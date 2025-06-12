from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import classonlymethod
import json
from langdetect import detect
from django.core.cache import cache
import hashlib
from .constants import SYSTEM_PROMPT, synonym_dict, INTENT_TO_CATEGORY_MAP, get_response_type
from .utils.filtering import is_malicious, Intent, INTENT_MESSAGES, is_travel_intent, analyze_user_input
from .services.translation import translate_to_korean, translate_to_original
from .services.gpt_service import call_openai_gpt, generate_follow_up_question
from .services.recommendation.recommender import get_recommendations, get_places_summary_by_contentids, get_nearby_recommendations
from .services.recommendation.user_profile import get_user_profile
from .utils.location_extractor import LocationExtractor
from .services.recommendation.score import expand_keywords_with_synonyms
import traceback
from .services.recommendation.recommender import metadata

def make_recommendation_cache_key(user_id: str, user_input: str) -> str:
    key_str = f"rec_cache:{user_id}:{user_input}"
    return f"rec_cache:{hashlib.md5(key_str.encode('utf-8')).hexdigest()}"

location_extractor = LocationExtractor()


class ChatbotAsyncView(View):
    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return csrf_exempt(view)

    async def post(self, request):
        print("\n\n" + "=" * 25 + " [START] New Chatbot Request " + "=" * 25)

        try:
            # --- [0] 요청 데이터 파싱 ---
            data = json.loads(request.body)
            user_input = data.get("message", "")
            user_id = data.get("user_id", "anonymous")
            context = data.get("context")
            print(f"✅ 요청 수신: user_id='{user_id}', message='{user_input[:50]}'")

            # ⭐️ [추가] 캐시 확인 (후속 질문이 아닐 경우에만)
            if not context:
                cache_key = make_recommendation_cache_key(user_id, user_input)
                cached_response = cache.get(cache_key)
                if cached_response:
                    print(f"✅ 캐시 히트! user_id='{user_id}', message='{user_input[:50]}'")
                    return JsonResponse(cached_response)

            # --- [1] 악성/길이 필터링 ---
            if is_malicious(user_input):
                return JsonResponse({"response": INTENT_MESSAGES[Intent.MALICIOUS], "results": []})
            if len(user_input) > 500:
                return JsonResponse({"response": "입력은 500자 이내로 해주세요.", "results": []}, status=400)

            # --- [2] 언어 감지 및 번역 ---
            lang = detect(user_input)
            if lang != "ko":
                original_lang = lang
                user_input = await translate_to_korean(user_input)
            else:
                original_lang = "ko"

            # --- [3] 후속 질문 응답 분기 ---
            response_type = get_response_type(user_input)
            print("response_type:", response_type)
            print("context:", context)
            if context:
                print("context exists:", context)
                follow_up_response = await self.handle_follow_up(context, response_type)
                print("follow_up_response:", follow_up_response)
                if follow_up_response:
                    return follow_up_response

            # --- [4] 사용자 입력 분석 ---
            try:
                analysis_result = analyze_user_input(user_input)
                intent_str = analysis_result.get("intent")
                response_message = analysis_result.get("message")
                keywords = analysis_result.get("keywords", [])
                extracted_locations = location_extractor.extract(user_input)
            except Exception as e:
                print(f"❌ 분석 실패: {e}")
                return JsonResponse({"response": "죄송합니다. 입력을 이해하는 데 문제가 생겼어요.", "results": []})

            # --- [5] 의도 확인 ---
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.UNKNOWN

                # ⭐️ [추가] '데이트 장소 추천' 의도에 대한 특별 처리
            if intent == Intent.RECOMMEND_DATE_SPOT:
                response_message = "네, 데이트하기 좋은 장소를 찾아드릴게요! 어떤 종류의 데이트를 원하세요?"

                # 프론트엔드에서 버튼으로 표시할 수 있는 제안 목록
                suggested_replies = [
                    "분위기 좋은 맛집이나 카페",
                    "재미있는 전시회나 공연",
                    "조용히 걷기 좋은 산책로나 공원",
                    "특별한 체험을 할 수 있는 곳"
                ]

                return JsonResponse({
                    "response": response_message,
                    "results": [],  # 추천 목록은 아직 없음
                    "suggested_replies": suggested_replies,  # ⭐️ 선택지를 전달
                    "context": None,  # 다음 턴은 새로운 시작
                })

                # 여행 관련 의도가 아니면 종료
            if not is_travel_intent(intent):
                return JsonResponse({
                    "response": INTENT_MESSAGES.get(intent, INTENT_MESSAGES[Intent.UNKNOWN]),
                    "results": []
                })

            # --- [6] 사용자 프로필 + 키워드 확장 ---
            user_profile = get_user_profile(user_id)
            expanded_keywords = expand_keywords_with_synonyms(keywords, synonym_dict)

            # --- [7] 장소 추천 생성 ---
            recommendations = await get_recommendations(
                user_input, user_profile, intent, expanded_keywords,
                extracted_locations=extracted_locations, top_n=5
            )
            contentids = [r['contentid'] for r in recommendations]
            places_summary = get_places_summary_by_contentids(contentids, metadata)

            # --- [8] 다국어 응답 처리 ---
            if original_lang != "ko":
                response_message = await translate_to_original(response_message, dest=original_lang)
                for place in places_summary:
                    place["title"] = await translate_to_original(place["title"], dest=original_lang)
                    place["addr"] = await translate_to_original(place["addr"], dest=original_lang)

            # --- [9] 후속 질문 및 context 생성 ---
            follow_up_question, follow_up_context = await generate_follow_up_question(user_input, intent, places_summary)
            # --- [10] 최종 응답 반환 ---
            final_response_data = {
                "response": response_message,
                "results": places_summary,
                "follow_up_question": follow_up_question,
                "context": follow_up_context,
            }
            if not context:
                cache.set(cache_key, final_response_data, timeout=3600)  # 1시간 동안 캐시
                print(f"✅ 캐시 저장 완료: key='{cache_key}'")
            print(final_response_data)
            return JsonResponse(final_response_data)

        except Exception as e:
            print(f"❌ 처리 중 예외 발생: {e}")
            return JsonResponse({"response": "죄송합니다. 서버에서 오류가 발생했습니다.", "results": []}, status=500)

    async def handle_follow_up(self, context, response_type):
        """
        [리팩토링] Context의 follow_up_type에 따라 적절한 처리 함수로 연결하는 디스패처
        """
        follow_up_type = context.get("follow_up_type")

        # 긍정적인 답변일 경우에만 분기 처리
        if response_type == "affirmative":
            if follow_up_type in ["nearby_tour", "nearby_food", "nearby_cafe"]:
                return await self.handle_nearby_recommendation(context)
            elif follow_up_type == "create_itinerary":
                # return await self.handle_itinerary_creation(context) # (미래 확장 예시)
                pass
            # ... 다른 타입의 후속 질문 핸들러 추가 ...

        # 부정적이거나 중립적인 답변 처리
        elif response_type == "negative":
            return JsonResponse({"response": "알겠습니다. 그럼 다른 도움이 필요하시면 말씀해주세요!", "results": [], "context": None})
        elif response_type == "neutral":
            return JsonResponse({"response": "혹시 아직 고민 중이신가요? 더 도와드릴 수 있어요!", "results": [], "context": context})

        return None  # 처리할 수 없는 경우 None을 반환하여 일반 파이프라인으로 넘김

    async def handle_nearby_recommendation(self, context):
        """
        '주변 추천' 유형의 후속 질문을 처리하는 전담 함수
        """
        anchor_ids = context.get("anchor_content_ids", [])
        target_intent_str = context.get("follow_up_intent_str", "")
        target_category_id = INTENT_TO_CATEGORY_MAP.get(target_intent_str)

        if not (anchor_ids and target_category_id):
            return None

        recommendations = await get_nearby_recommendations(anchor_ids, target_category_id)
        places_summary = get_places_summary_by_contentids([p['contentid'] for p in recommendations], metadata)

        # 여기서도 언어 번역이 필요하다면 추가해야 합니다.

        return JsonResponse({
            "response": "네, 그럼요! 방금 추천해드린 장소들 근처에 가볼 만한 곳들이에요.",
            "results": places_summary,
            "context": None,  # 후속 질문의 후속 질문은 없도록 context 초기화
        })

