from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import classonlymethod
import json
from langdetect import detect
from django.core.cache import cache

from .constants import SYSTEM_PROMPT
from .utils.filtering import is_malicious, is_travel_related
from .services.translation import translate_to_korean, translate_to_original
from .services.gpt_service import call_openai_gpt
from .services.recommendation.formatter import format_as_cards
from .services.recommendation.recommender import get_recommendations
from .services.recommendation.profile import get_user_profile
from .utils.filtering import analyze_user_input

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

        # ⚡ 3. 캐시 확인 (중복 GPT 요청 방지)
        cache_key = f"gpt_cache:{user_input}"
        cached_response = cache.get(cache_key)
        if cached_response:
            result = cached_response
        else:
            # 🌏 4. 여행 관련 여부 판단
            if not is_travel_related(user_input):
                result = "저는 여행 관련 추천만 도와드릴 수 있어요. 예: '서울 2박 3일 여행 코스 추천해줘'"
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
        recommendations = await get_recommendations(
            query=user_input,
            user_profile=user_profile,
            intent=intent,
            keywords=keywords
        )

        # 🧾 8. 카드 형태로 변환
        cards = format_as_cards(recommendations)

        # 🌍 9. 결과 번역 (사용자가 한국어가 아닐 경우)
        if original_lang != "ko":
            result = await translate_to_original(result, dest=original_lang)
            for card in cards:
                card["title"] = await translate_to_original(card["title"], dest=original_lang)
                card["overview"] = await translate_to_original(card["overview"], dest=original_lang)
                #card["reason"] = await translate_to_original(card["reason"], dest=original_lang)
            # ✨ 일정 추천도 있다면 아래 부분 주석 해제
            # for day in schedule:
            #     for i in range(len(schedule[day])):
            #         schedule[day][i]["title"] = await translate_to_original(schedule[day][i]["title"], dest=original_lang)

        # 📤 10. 최종 응답 반환
        return JsonResponse({
            "response": result,
            "recommendations": cards,
            # "schedule": schedule
        })
