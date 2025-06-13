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
from .services.gpt_service import call_openai_gpt, generate_follow_up_question, create_itinerary_with_gpt
from .services.recommendation.recommender import get_recommendations, get_places_summary_by_contentids, get_nearby_recommendations
from .services.recommendation.user_profile import get_user_profile
from .utils.location_extractor import LocationExtractor
from .services.recommendation.score import expand_keywords_with_synonyms
import traceback
from .services.recommendation.recommender import metadata
import ast

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
            user_location = data.get("location")

            # 프론트에서 문자열화된 dict가 넘어올 경우를 대비한 방어 코드
            if isinstance(user_location, str):
                try:
                    user_location = ast.literal_eval(user_location)
                except:
                    user_location = None

            print(f"✅ 요청 수신: user_id='{user_id}', message='{user_input[:50]}', user_location={user_location}")

            # --- [1] 캐시 확인 (후속 질문이 아닐 경우) ---
            if not context:
                cache_key = make_recommendation_cache_key(user_id, user_input)
                cached_response = cache.get(cache_key)
                if cached_response:
                    print(f"✅ 캐시 히트!")
                    return JsonResponse(cached_response)

            # --- [2] 악성/길이 필터링 ---
            if is_malicious(user_input):
                return JsonResponse({"response": INTENT_MESSAGES[Intent.MALICIOUS], "results": []})
            if len(user_input) > 500:
                return JsonResponse({"response": "입력은 500자 이내로 해주세요."}, status=400)

            # --- [3] 언어 감지 및 번역 ---
            lang = detect(user_input)
            original_lang = "ko"
            if lang != "ko":
                original_lang = lang
                user_input = await translate_to_korean(user_input)

            # --- [4] 후속 질문(Context) 우선 처리 ---
            if context:
                response_type = get_response_type(user_input)
                follow_up_response = await self.handle_follow_up(context, response_type)
                if follow_up_response:
                    return follow_up_response

            # --- [5] 새로운 요청에 대한 통합 분석 ---
            analysis_result = analyze_user_input(user_input)
            intent = Intent(analysis_result.get("intent", "unknown"))
            keywords = analysis_result.get("keywords", [])
            extracted_locations = location_extractor.extract(user_input)

            # --- [6] ⭐️ 의사결정 로직: 추천 모드 결정 ---
            is_nearby_query = any(kw in user_input for kw in ['근처', '주변', '가까운', '여기', '이 근처', '내 위치'])

            # 1순위: 주변 추천
            if is_nearby_query and user_location:
                print("🚦 DECISION: '주변 추천' 모드로 진입")
                # '주변 추천' 의도를 강제하여 recommender가 올바르게 작동하도록 함
                recommendations = await get_recommendations(
                    user_input, get_user_profile(user_id), Intent.RECOMMEND_NEARBY,
                    keywords, extracted_locations, user_location, top_n=5
                )
                response_message = analysis_result.get("message")  # 원래 분석된 메시지 사용

            # 2순위: 데이트 장소 되묻기
            elif intent == Intent.RECOMMEND_DATE_SPOT:
                print("🚦 DECISION: '데이트 장소 되묻기' 모드로 진입")
                return JsonResponse({
                    "response": "네, 데이트하기 좋은 장소를 찾아드릴게요! 어떤 종류의 데이트를 원하세요?",
                    "results": [],
                    "suggested_replies": [
                        "분위기 좋은 맛집이나 카페", "재미있는 전시회나 공연",
                        "조용히 걷기 좋은 산책로나 공원", "특별한 체험을 할 수 있는 곳"
                    ],
                    "context": None,
                })

            # 3순위: 일반 여행 추천
            elif is_travel_intent(intent):
                print("🚦 DECISION: '일반 여행 추천' 모드로 진입")
                recommendations = await get_recommendations(
                    user_input, get_user_profile(user_id), intent,
                    expand_keywords_with_synonyms(keywords, synonym_dict),
                    extracted_locations, top_n=5
                )
                response_message = analysis_result.get("message")

            # 4순위: 여행 외 응답
            else:
                print("🚦 DECISION: '여행 외' 의도로 판단하여 종료")
                return JsonResponse({
                    "response": INTENT_MESSAGES.get(intent, INTENT_MESSAGES[Intent.UNKNOWN]),
                    "results": []
                })

            # --- [7] 추천 결과 후처리 ---
            contentids = [r['contentid'] for r in recommendations]
            places_summary = get_places_summary_by_contentids(contentids, metadata)

            if original_lang != "ko":
                response_message = await translate_to_original(response_message, dest=original_lang)
                for place in places_summary:
                    place["title"] = await translate_to_original(place["title"], dest=original_lang)
                    place["addr"] = await translate_to_original(place["addr"], dest=original_lang)

            # --- [8] 후속 질문 및 context 생성 ---
            follow_up_question, follow_up_context = await generate_follow_up_question(user_input, intent,
                                                                                      places_summary)

            # --- [9] 최종 응답 및 캐시 저장 ---
            final_response_data = {
                "response": response_message, "results": places_summary,
                "follow_up_question": follow_up_question, "context": follow_up_context,
            }
            if not context:  # 캐시는 최초 요청에 대해서만 저장
                cache.set(make_recommendation_cache_key(user_id, user_input), final_response_data, timeout=3600)

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


class TripPlannerView(View):
    """
    '여행 장바구니'와 관련된 기능을 처리하는 View
    """

    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return csrf_exempt(view)

    async def post(self, request):
        """'코스 만들어줘' 요청을 처리하여 GPT로 일정을 생성합니다."""
        # 1. 세션에서 장바구니(담아둔 contentid 리스트)를 가져옵니다.
        trip_cart_ids = request.session.get('trip_cart', [])

        if len(trip_cart_ids) < 2:
            return JsonResponse({"error": "코스를 만들려면 최소 2개 이상의 장소를 선택해야 합니다."}, status=400)

        # 2. 이전에 만든 GPT 일정 생성기 호출
        itinerary_data = await create_itinerary_with_gpt(trip_cart_ids)

        if not itinerary_data:
            return JsonResponse({"error": "일정 생성에 실패했습니다."}, status=500)

        # 3. 성공 시, 생성된 일정과 함께 세션의 장바구니는 비워줍니다.
        request.session['trip_cart'] = []

        return JsonResponse({"itinerary": itinerary_data})

    async def put(self, request):
        """장바구니에 장소를 '추가'합니다."""
        data = json.loads(request.body)
        contentid = data.get('contentid')
        if not contentid:
            return JsonResponse({"error": "contentid가 필요합니다."}, status=400)

        # 세션에서 장바구니를 가져오거나, 없으면 새로 만듭니다.
        trip_cart = request.session.get('trip_cart', [])

        # 중복 추가 방지
        if contentid not in trip_cart:
            trip_cart.append(contentid)

        # 변경된 장바구니를 세션에 다시 저장
        request.session['trip_cart'] = trip_cart

        return JsonResponse({"success": True, "cart_count": len(trip_cart)})

    async def delete(self, request):
        """장바구니에서 장소를 '삭제'합니다."""
        data = json.loads(request.body)
        contentid = data.get('contentid')
        if not contentid:
            return JsonResponse({"error": "contentid가 필요합니다."}, status=400)

        trip_cart = request.session.get('trip_cart', [])
        if contentid in trip_cart:
            trip_cart.remove(contentid)

        request.session['trip_cart'] = trip_cart

        return JsonResponse({"success": True, "cart_count": len(trip_cart)})

