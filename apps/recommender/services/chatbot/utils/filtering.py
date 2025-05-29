import re
from enum import Enum
from ..constants import FORBIDDEN_PATTERNS


# ✅ 1. 의도 라벨을 Enum으로 통합
class Intent(str, Enum):
    RECOMMEND_TOUR = "recommend_tour"
    RECOMMEND_FOOD = "recommend_food"
    RECOMMEND_SHOPPING = "recommend_shopping"
    RECOMMEND_FESTIVAL = "recommend_festival"
    RECOMMEND_ACTIVITY = "recommend_activity"
    RECOMMEND_NATURE = "recommend_nature"
    RECOMMEND_HISTORY = "recommend_history"
    RECOMMEND_LEISURE = "recommend_leisure"
    RECOMMEND_QUITE = "recommend_quite"
    MALICIOUS = "malicious"
    UNKNOWN = "unknown"


# ✅ 2. intent별 정규표현식 패턴 정의
INTENT_PATTERNS = {
    Intent.RECOMMEND_TOUR: [
        r"(여행|관광|명소|가볼만한\s*곳|추천\s*(코스|장소|일정)?|일정\s*짜줘)",
        r"(힐링|캠핑|도보|가족|나홀로|맛집)\s*(코스|여행)",
    ],
    Intent.RECOMMEND_FOOD: [
        r"(맛집|먹거리|식당|음식점|카페|주점|간식|한식|중식|일식|분식|퓨전음식)",
    ],
    Intent.RECOMMEND_SHOPPING: [
        r"(쇼핑|백화점|아울렛|시장|면세점|기념품\s*가게|쇼핑몰|상점)",
    ],
    Intent.RECOMMEND_FESTIVAL: [
        r"(축제|행사|페스티벌|공연|전시회|콘서트|박람회|뮤지컬|영화|문화\s*행사)",
    ],
    Intent.RECOMMEND_ACTIVITY: [
        r"(체험|사찰|템플스테이|공예|목장|농장|유람선|스파|온천|힐링명상|웰니스)",
    ],
    Intent.RECOMMEND_NATURE: [
        r"(산|계곡|강|호수|바다|해수욕장|공원|숲|동굴|정원|자연|폭포)",
    ],
    Intent.RECOMMEND_HISTORY: [
        r"(역사|유적지|고궁|사찰|종교|성지|민속마을|탑|불상|전통문화|안보)",
    ],
    Intent.RECOMMEND_LEISURE: [
        r"(스포츠|레저|수영|낚시|자전거|하이킹|스키|승마|래프팅|카약|캠핑)",
    ],
    Intent.RECOMMEND_QUITE: [
        r"(조용한|한적한|사람\s*없는|숨은\s*명소|한산한|힐링\s*여행|숨트여)",
    ],
}


# ✅ 3. intent별 사용자 응답 메시지 정의
INTENT_MESSAGES = {
    Intent.RECOMMEND_TOUR: "관광지를 추천해드릴게요. 여행 스타일(예: 힐링, 가족, 나홀로)에 맞는 코스를 찾아보는 중입니다.",
    Intent.RECOMMEND_FOOD: "지역 내 맛집을 추천해드릴게요. 선호하는 음식이 있다면 알려주세요!",
    Intent.RECOMMEND_SHOPPING: "쇼핑하기 좋은 장소를 찾고 있어요. 대형 쇼핑몰부터 기념품점까지 다양하게 추천해드릴게요.",
    Intent.RECOMMEND_FESTIVAL: "지금 열리는 축제나 문화 행사를 찾아드릴게요!",
    Intent.RECOMMEND_ACTIVITY: "색다른 체험 활동을 원하시나요? 관련 체험 관광지를 추천해드릴게요.",
    Intent.RECOMMEND_NATURE: "자연 속으로 떠나볼까요? 산, 계곡, 바다 같은 자연 관광지를 찾아보는 중입니다.",
    Intent.RECOMMEND_HISTORY: "역사와 문화를 느낄 수 있는 유적지나 사찰을 추천해드릴게요.",
    Intent.RECOMMEND_LEISURE: "레저 스포츠나 액티비티를 즐기고 싶으시군요! 관련된 장소를 찾아드릴게요.",
    Intent.RECOMMEND_QUITE: "북적이지 않아 좋은, 감성 한 스푼 여행지 추천 해드릴게요."
    Intent.UNKNOWN: "죄송해요, 요청하신 내용을 정확히 이해하지 못했어요. 다시 한번 말씀해주시겠어요?",
    Intent.MALICIOUS: "저는 여행 관련 추천만 도와드릴 수 있어요. 예: '서울 2박 3일 여행 코스 추천해줘'",
}


# ✅ 4. 금지 패턴 탐지
def is_malicious(text: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FORBIDDEN_PATTERNS)


# ✅ 5. 키워드 정규표현식 추출
def extract_intent_keywords(text: str):
    keyword_hits = {}
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                keyword_hits[intent] = keyword_hits.get(intent, []) + matches
    return keyword_hits


# ✅ 6. 가장 유력한 intent 판단
def classify_intent(text: str) -> Intent:
    keyword_hits = extract_intent_keywords(text)
    if not keyword_hits:
        return Intent.UNKNOWN
    # 매칭 키워드 수가 가장 많은 intent 선택
    sorted_intents = sorted(keyword_hits.items(), key=lambda x: len(x[1]), reverse=True)
    return sorted_intents[0][0]


# ✅ 7. 최종 분석 함수
def analyze_user_input(text: str):
    if is_malicious(text):
        return {
            "intent": Intent.MALICIOUS.value,
            "message": INTENT_MESSAGES[Intent.MALICIOUS],
            "keywords": [],
        }

    intent = classify_intent(text)
    keywords = extract_intent_keywords(text).get(intent, [])

    return {
        "intent": intent.value,
        "message": INTENT_MESSAGES[intent],
        "keywords": list(set(keywords)),  # 중복 제거
    }


# ✅ 8. 여행 관련 intent 여부 판단
def is_travel_related(text: str) -> bool:
    result = analyze_user_input(text)
    intent = result.get("intent")
    return intent in {i.value for i in [
        Intent.RECOMMEND_TOUR,
        Intent.RECOMMEND_FOOD,
        Intent.RECOMMEND_SHOPPING,
        Intent.RECOMMEND_FESTIVAL,
        Intent.RECOMMEND_ACTIVITY,
        Intent.RECOMMEND_NATURE,
        Intent.RECOMMEND_HISTORY,
        Intent.RECOMMEND_LEISURE,
        Intent.RECOMMEND_QUITE,
    ]}
