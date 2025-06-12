import httpx
import os
from dotenv import load_dotenv
from typing import Tuple, Optional, List
from ..constants import Intent

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")


async def call_openai_gpt(messages, temperature=0.7, max_tokens=300):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {openai_api_key}"},
            json={
                "model": "gpt-3.5-turbo",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=15
        )
        response.raise_for_status()

        # 확실히 JSON으로 파싱하고 출력 확인
        data = response.json()
        print("[DEBUG] GPT 응답 JSON:", data)  # ✅ 디버깅용 출력

        return data["choices"][0]["message"]["content"]
# services/gpt_service.py (또는 유사한 파일)에 추가


# ⭐️ [변경점 1] 후속 질문 규칙을 딕셔너리로 중앙 관리
# 나중에 새로운 규칙(예: 일정 짜주기)을 추가하기 매우 용이합니다.
FOLLOW_UP_RULES = {
    Intent.RECOMMEND_FOOD: {"type": "nearby_tour", "next_intent": Intent.RECOMMEND_TOUR,
                            "suggestion": "주변 관광 명소나 예쁜 카페"},
    Intent.RECOMMEND_TOUR: {"type": "nearby_food", "next_intent": Intent.RECOMMEND_FOOD,
                            "suggestion": "근처 맛집이나 식사할 만한 곳"},
    Intent.RECOMMEND_NATURE: {"type": "nearby_cafe", "next_intent": Intent.RECOMMEND_FOOD,
                              "suggestion": "근처에서 쉴 만한 감성 카페"},
    Intent.RECOMMEND_HISTORY: {"type": "nearby_food", "next_intent": Intent.RECOMMEND_FOOD,
                               "suggestion": "근처의 전통 찻집이나 식사할 곳"},
    Intent.RECOMMEND_ACTIVITY: {"type": "nearby_food", "next_intent": Intent.RECOMMEND_FOOD,
                                "suggestion": "활동 후 허기를 달랠 맛집"},
    Intent.RECOMMEND_LEISURE: {"type": "nearby_food", "next_intent": Intent.RECOMMEND_FOOD,
                               "suggestion": "레저 활동 후 에너지를 보충할 맛집"},
    Intent.RECOMMEND_SHOPPING: {"type": "nearby_cafe", "next_intent": Intent.RECOMMEND_FOOD,
                                "suggestion": "쇼핑 중 잠시 쉴 수 있는 카페"},
    # 'recommend_quiet'는 단독으로 끝나는 경우가 많아 일부러 제외
}


# ⭐️ [변경점 2] 반환 타입을 튜플로 변경: (질문 문자열, context 딕셔너리 또는 None)
async def generate_follow_up_question(original_query: str, intent: Intent, recommendations: list) -> Tuple[
    str, Optional[dict]]:
    """
    [수정] 사용자의 쿼리와 추천 결과를 바탕으로, 자연스러운 후속 질문과 다음 행동을 정의하는 context를 생성합니다.
    """
    # 추천 결과가 없거나, 후속 질문 규칙에 없는 의도일 경우 빈 값 반환
    if not recommendations or intent not in FOLLOW_UP_RULES:
        return "", None

    # ⭐️ [변경점 3] if/elif 대신 규칙 딕셔너리에서 다음 행동을 바로 조회
    rule = FOLLOW_UP_RULES[intent]
    follow_up_suggestion = rule["suggestion"]

    # GPT에 전달할 추천 목록 텍스트 생성
    reco_titles = ", ".join([f"'{item['title']}'" for item in recommendations])

    # --- GPT 프롬프트 설계 (기존과 유사) ---
    system_prompt = "당신은 사용자의 여행 계획을 돕는 친절하고 눈치 빠른 여행 비서입니다."
    user_prompt = f"""
    사용자가 방금 아래와 같은 질문을 했고, 당신은 몇 군데 장소를 추천해 주었습니다.
    - 사용자의 원래 질문: "{original_query}"
    - 당신이 추천한 장소들: {reco_titles}

    이제 대화를 자연스럽게 이어나가기 위해, 다음 제안을 바탕으로 사용자에게 할 유도 질문을 한 문장으로 생성해주세요.

    - 다음 제안 내용: "{follow_up_suggestion}"

    조건:
    1. 예의 바르고 친근한 말투를 사용하세요.
    2. 사용자에게 선택권을 주는 형태로 질문하세요. (예: ~도 찾아드릴까요?, ~는 어떠세요?)
    3. 너무 길지 않게, 한 문장으로 간결하게 만들어주세요.

    생성할 유도 질문:
    """

    try:
        # GPT 호출하여 질문 텍스트 생성
        question_text = await call_openai_gpt(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=100
        )
        question_text = question_text.strip()

        # ⭐️ [변경점 4] 다음 대화를 위한 context 객체 생성
        follow_up_context = {
            "follow_up_type": rule["type"],
            "follow_up_intent_str": rule["next_intent"].value,
            "anchor_content_ids": [p['contentid'] for p in recommendations]
        }

        # 튜플 형태로 반환
        return question_text, follow_up_context

    except Exception as e:
        print(f"후속 질문 생성 중 오류 발생: {e}")
        return "", None  # 오류 발생 시 빈 튜플 반환