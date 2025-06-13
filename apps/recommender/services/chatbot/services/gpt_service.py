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


async def generate_follow_up_question(original_query: str, intent: Intent, recommendations: list) -> Tuple[
    str, Optional[dict]]:
    """
    [수정] '코스에 추가' 기능을 안내하는 문구를 포함하도록 GPT 프롬프트를 수정합니다.
    """
    if not recommendations or intent not in FOLLOW_UP_RULES:
        return "", None

    rule = FOLLOW_UP_RULES[intent]
    follow_up_suggestion = rule["suggestion"]
    reco_titles = ", ".join([f"'{item['title']}'" for item in recommendations])

    # --- ⭐️ GPT 프롬프트 수정 (핵심 변경점) ⭐️ ---
    system_prompt = "당신은 사용자의 여행 계획을 돕는 친절하고 눈치 빠른 여행 비서입니다."
    user_prompt = f"""
    사용자가 방금 아래와 같은 질문을 했고, 당신은 몇 군데 장소를 추천해 주었습니다.
    - 사용자의 원래 질문: "{original_query}"
    - 당신이 추천한 장소들: {reco_titles}

    이제 대화를 자연스럽게 이어나가기 위해, 아래 두 가지 내용을 모두 포함하여 사용자에게 할 유도 질문을 한두 문장으로 생성해주세요.

    ### 반드시 포함할 내용
    1.  **코스 추가 안내:** "마음에 드는 곳이 있다면 '코스에 추가' 버튼을 눌러 나만의 여행 계획을 만들어보세요." 와 같은, 사용자가 '코스 추가' 기능을 사용하도록 유도하는 친절한 안내 문구.
    2.  **후속 질문:** 아래 '다음 제안 내용'을 바탕으로 대화를 이어나갈 자연스러운 질문.

    - 다음 제안 내용: "{follow_up_suggestion}"

    ### 응답 형식
    - 안내 문구와 후속 질문을 자연스럽게 한두 문장으로 연결해주세요.
    - 예시: "추천해드린 곳 중 마음에 드는 곳은 '코스에 추가' 버튼으로 담아둘 수 있어요. 혹시 이 맛집들 근처에서 가볍게 둘러볼 관광지도 찾아드릴까요?"

    생성할 유도 질문:
    """

    try:
        question_text = await call_openai_gpt(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=150  # 문장이 길어졌으므로 토큰 수 약간 증가
        )
        question_text = question_text.strip().replace('"', '')

        follow_up_context = {
            "follow_up_type": rule["type"],
            "follow_up_intent_str": rule["next_intent"].value,
            "anchor_content_ids": [p['contentid'] for p in recommendations]
        }

        return question_text, follow_up_context

    except Exception as e:
        print(f"후속 질문 생성 중 오류 발생: {e}")
        return "", None


async def create_itinerary_with_gpt(place_content_ids: list) -> dict:
    """
    주어진 장소 ID 목록을 바탕으로, GPT를 이용해 반나절 여행 코스를 생성합니다.
    결과는 구조화된 JSON 형태로 반환됩니다.
    """
    if not place_content_ids:
        return {}

    # 1. contentid를 기반으로 각 장소의 상세 정보 조회
    places_data = []
    for cid in place_content_ids:
        item = metadata.get(cid)
        if item:
            places_data.append({
                "id": cid,
                "title": item.get("title"),
                "category": item.get("cat3"),  # 예시: '한식', '자연관광' 등
                "address": item.get("addr1")
            })

    # GPT에게 전달하기 좋은 형태로 데이터 변환
    input_places_json_string = json.dumps(places_data, ensure_ascii=False, indent=2)

    # 2. ⭐️ GPT 프롬프트 설계 (매우 중요)
    system_prompt = "당신은 부산 지역 전문 여행 플래너입니다. 주어진 장소 목록을 가지고, 사용자가 만족할 만한 최적의 여행 코스를 제안하는 역할을 합니다."
    user_prompt = f"""
    아래 장소 목록을 사용하여, 사용자를 위한 매력적인 '반나절 여행 코스'를 짜주세요.

    ### 장소 목록 (JSON)
    {input_places_json_string}

    ### 코스 생성 규칙
    1.  **논리적 순서:** 식사, 관광, 카페 등의 순서를 고려하여 동선이 자연스럽게 이어지도록 순서를 정해주세요.
    2.  **코스 제목:** 전체 코스를 아우르는 매력적인 제목을 지어주세요. (예: "해운대 미식과 바다를 품은 힐링 반나절")
    3.  **단계별 설명:** 각 단계(장소)마다 이동 방법(예: '도보 10분', '택시로 기본요금 거리')과 추천 활동, 예상 소요 시간을 간략하고 재미있게 설명해주세요.
    4.  **JSON 출력:** 최종 결과는 반드시 아래와 같은 JSON 형식으로만 응답해주세요.

    ### 출력 JSON 형식
    {{
      "itinerary_title": "코스 전체 제목",
      "steps": [
        {{
          "step": 1,
          "title": "첫 번째 장소 이름",
          "description": "이곳에서 할 활동과 간단한 팁. (예: 먼저 이곳에서 든든하게 점심을 해결하세요!)",
          "estimated_duration": "1시간 30분"
        }},
        {{
          "step": 2,
          "title": "두 번째 장소 이름",
          "description": "식사 후 가볍게 산책하기 좋은 곳입니다. 멋진 사진을 남겨보세요.",
          "estimated_duration": "1시간"
        }},
        {{
          "step": 3,
          "title": "세 번째 장소 이름",
          "description": "여행의 마무리로, 이곳의 시그니처 커피를 마시며 여유를 즐겨보세요.",
          "estimated_duration": "1시간"
        }}
      ]
    }}
    """

    try:
        # GPT-4-turbo나 JSON 모드를 지원하는 최신 모델 사용 권장
        response_json_str = await call_openai_gpt(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.6,
            response_format={"type": "json_object"}
        )
        return json.loads(response_json_str)
    except Exception as e:
        print(f"일정 생성 중 오류 발생: {e}")
        return {}