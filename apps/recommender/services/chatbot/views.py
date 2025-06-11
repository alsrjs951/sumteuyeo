from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import classonlymethod
import json
from langdetect import detect
from django.core.cache import cache
import hashlib
from .constants import SYSTEM_PROMPT, synonym_dict
from .utils.filtering import is_malicious, is_travel_related
from .services.translation import translate_to_korean, translate_to_original
from .services.gpt_service import call_openai_gpt
from .services.recommendation.recommender import get_recommendations, get_places_summary_by_contentids
from .services.recommendation.user_profile import get_user_profile
from .services.recommendation.score import expand_keywords_with_synonyms
from .utils.filtering import analyze_user_input

# metadata는 spot_metadata.json을 미리 딕셔너리로 로드해둔 객체라고 가정
from .services.recommendation.recommender import metadata

def make_cache_key(user_input):
    key_str = f"gpt_cache:{user_input}"
    key_hash = hashlib.md5(key_str.encode('utf-8')).hexdigest()
    return f"gpt_cache:{key_hash}"
class ChatbotAsyncView(View):
    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return csrf_exempt(view)

    async def post(self, request):
        data = json.loads(request.body)
        user_input = data.get("message", "")
        user_id = data.get("user_id", "anonymous")

        # 🚨 1. 악성 요청 필터링
        if is_malicious(user_input):
            return JsonResponse({"response": "비정상적인 요청이 감지되었습니다."}, status=400)
        if len(user_input) > 500:
            return JsonResponse({"response": "입력은 500자 이내로 해주세요."}, status=400)

        # 🌐 2. 언어 감지 및 번역
        lang = detect(user_input)
        if lang != "ko":
            original_lang = lang
            user_input = await translate_to_korean(user_input)
        else:
            original_lang = "ko"

        # ⚡ 3. 캐시 확인 (중복 GPT 요청 방지, 안전한 키 사용)
        cache_key = make_cache_key(user_input)
        cached_response = cache.get(cache_key)
        if cached_response:
            result = cached_response
        else:
            # 🌏 4. 여행 관련 여부 판단
            if not is_travel_related(user_input):
                result = "저는 여행 관련 추천만 도와드릴 수 있어요. 예: '부산에서 혼자 즐기기 좋은 자연 관광지 추천해줘'"
            else:
                try:
                    # 💡 GPT 시스템 메시지 + 사용자 입력 전달
                    messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_input}
                    ]
                    result = await call_openai_gpt(messages)
                    cache.set(cache_key, result, timeout=3600)
                except Exception:
                    return JsonResponse({"response": "GPT 호출 중 오류가 발생했습니다."}, status=500)
        # 👤 5. 사용자 프로필 불러오기
        user_profile = get_user_profile(user_id)

        # 🔍 6. 사용자 입력 intent 및 keywords 분석
        intent_result = analyze_user_input(user_input)
        intent = intent_result.get("intent")
        keywords = intent_result.get("keywords", [])

        # 📌 7. 추천 결과 생성 (의도 + 키워드 반영)
        expanded_keywords = expand_keywords_with_synonyms(keywords, synonym_dict)
        recommendations = await get_recommendations(user_input, user_profile, intent, expanded_keywords, top_n=5)
        contentids = [item['contentid'] for item in recommendations]
        places_summary = get_places_summary_by_contentids(contentids, metadata)

        # 🌍 8. 결과 번역 (사용자가 한국어가 아닐 경우)
        if original_lang != "ko":
            result = await translate_to_original(result, dest=original_lang)
            for place in places_summary:
                place["title"] = await translate_to_original(place["title"], dest=original_lang)
                place["addr"] = await translate_to_original(place["addr"], dest=original_lang)
                # 필요시 tel, firstimage 등도 번역 가능

        print(places_summary)
        # 📤 9. 최종 응답 반환
        return JsonResponse({
            "response": result,  # 안내 메시지
        })

