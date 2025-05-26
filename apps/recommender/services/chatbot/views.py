from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import classonlymethod
import json
from langdetect import detect
from django.core.cache import cache

from chatbot.constants import SYSTEM_PROMPT
from chatbot.utils.filtering import is_malicious, is_travel_related
from chatbot.services.translation import translate_to_korean, translate_to_original
from chatbot.services.gpt_service import call_openai_gpt
from chatbot.services.recommendation import (
    get_user_profile,
    get_recommendations,
    format_as_cards,
    generate_schedule
)

class ChatbotAsyncView(View):
    @classonlymethod
    def as_view(cls, **initkwargs):
        view = super().as_view(**initkwargs)
        return csrf_exempt(view)

    async def post(self, request):
        data = json.loads(request.body)
        user_input = data.get("message", "")
        user_id = data.get("user_id", "anonymous")

        if is_malicious(user_input):
            return JsonResponse({"response": "비정상적인 요청이 감지되었습니다."}, status=400)
        if len(user_input) > 500:
            return JsonResponse({"response": "입력은 500자 이내로 해주세요."}, status=400)

        lang = detect(user_input)
        if lang != "ko":
            original_lang = lang
            user_input = await translate_to_korean(user_input)
        else:
            original_lang = "ko"

        cache_key = f"gpt_cache:{user_input}"
        cached_response = cache.get(cache_key)
        if cached_response:
            result = cached_response
        else:
            if not is_travel_related(user_input):
                result = "저는 여행 관련 추천만 도와드릴 수 있어요. 예: '서울 2박 3일 여행 코스 추천해줘'"
            else:
                try:
                    messages = [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_input}
                    ]
                    result = await call_openai_gpt(messages)
                    cache.set(cache_key, result, timeout=3600)
                except Exception:
                    return JsonResponse({"response": "GPT 호출 중 오류가 발생했습니다."}, status=500)

        user_profile = get_user_profile(user_id)
        recommendations = await get_recommendations(user_input, user_profile)
        cards = format_as_cards(recommendations)
        schedule = generate_schedule(recommendations)

        if original_lang != "ko":
            result = await translate_to_original(result, dest=original_lang)
            for card in cards:
                card["title"] = await translate_to_original(card["title"], dest=original_lang)
                card["overview"] = await translate_to_original(card["overview"], dest=original_lang)
                card["reason"] = await translate_to_original(card["reason"], dest=original_lang)
            for day in schedule:
                for i in range(len(schedule[day])):
                    schedule[day][i]["title"] = await translate_to_original(schedule[day][i]["title"], dest=original_lang)

        return JsonResponse({
            "response": result,
            "recommendations": cards,
            "schedule": schedule
        })
