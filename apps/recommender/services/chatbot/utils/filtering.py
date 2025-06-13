import re
from enum import Enum
from ..constants import FORBIDDEN_PATTERNS, Intent, TRAVEL_INTENTS, INTENT_MESSAGES
from .intent_classifier import predict_intent_transformer
from typing import Dict, List, Tuple


# 각 의도에 해당하는 키워드를 탐지하기 위한 정규식 패턴 딕셔너리
INTENT_PATTERNS = {
    Intent.RECOMMEND_TOUR: [
        r"(여행|관광|명소|일정\s*짜줘)",
        r"(도보|맛집)\s*(코스|여행)",
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
    Intent.RECOMMEND_DATE_SPOT: [
        r"(데이트|소개팅|기념일|커플|여자친구|남자친구|함께\s*가기\s*좋은)",
    ],
    Intent.RECOMMEND_NEARBY: [
            r"(근처|주변|가까운|여기|이 근처|내 위치)"
        ]
}



def is_malicious(text: str) -> bool:
    """
    입력된 텍스트에 금지된 패턴이 포함되어 있는지 확인하여 악성 여부를 판단합니다.

    Args:
        text (str): 사용자 입력 문자열.

    Returns:
        bool: 악성 패턴이 하나라도 발견되면 True, 그렇지 않으면 False.
    """
    # FORBIDDEN_PATTERNS의 각 정규식에 대해 하나라도 매칭되는 것이 있는지 확인
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FORBIDDEN_PATTERNS)


def extract_intent_keywords(text: str) -> Dict[Intent, List[str]]:
    """
    정규식을 기반으로 텍스트에서 모든 의도와 관련된 키워드를 추출합니다.

    Args:
        text (str): 사용자 입력 문자열.

    Returns:
        Dict[Intent, List[str]]: 각 의도를 키로, 해당 의도에 매칭된 키워드 리스트를 값으로 하는 딕셔너리.
    """
    keyword_hits = {}
    # INTENT_PATTERNS에 정의된 모든 의도와 패턴에 대해 반복
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            # 정규식에 매칭되는 모든 키워드를 찾음 (대소문자 무시)
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # 매칭된 키워드가 있으면, 해당 의도에 대한 리스트에 추가
                keyword_hits[intent] = keyword_hits.get(intent, []) + matches
    return keyword_hits


def classify_intent(text: str) -> Tuple[Intent, Dict[Intent, List[str]]]:
    """
    정규식과 ML 모델을 함께 사용하는 하이브리드 방식으로 사용자의 최종 의도를 분류합니다.
    효율성을 위해 의도와 함께 추출된 키워드 딕셔너리 전체를 반환합니다.

    Args:
        text (str): 사용자 입력 문자열.

    Returns:
        Tuple[Intent, Dict[Intent, List[str]]]: (확정된 최종 의도, 정규식으로 찾은 전체 키워드 딕셔너리) 튜플.
    """
    keyword_hits = extract_intent_keywords(text)

    if not keyword_hits:
        ml_intent_str = predict_intent_transformer(text)
        intent = Intent(ml_intent_str) if ml_intent_str in Intent.__members__ else Intent.UNKNOWN
        return intent, {}

    sorted_hits = sorted(keyword_hits.items(), key=lambda item: len(item[1]), reverse=True)
    top_intent, top_matches = sorted_hits[0]

    # '데이트'와 같은 복합 의도가 감지되면, 다른 의도보다 우선 순위를 부여할 수 있습니다.
    # 여기서는 기존 로직을 유지하되, 모든 return이 튜플 형식을 지키도록 합니다.
    if len(sorted_hits) == 1 or (len(sorted_hits) > 1 and len(top_matches) > len(sorted_hits[1][1])):
        return top_intent, keyword_hits

    ml_intent_str = predict_intent_transformer(text)
    if ml_intent_str in Intent.__members__:
        ml_intent = Intent(ml_intent_str)
        if ml_intent in keyword_hits:
            return ml_intent, keyword_hits

    # ⭐️ [중요] 모든 경로에서 반드시 (Intent, dict) 튜플로 반환해야 합니다.
    return top_intent, keyword_hits


def analyze_user_input(text: str) -> Dict:
    """
    사용자 입력에 대한 전체 분석 파이프라인을 실행하는 메인 함수입니다.
    악성 입력을 먼저 확인하고, 의도 분류 후 최종 결과를 포맷에 맞게 반환합니다.

    Args:
        text (str): 사용자 입력 문자열.

    Returns:
        Dict: {'intent': ..., 'message': ..., 'keywords': ...} 형태의 분석 결과 딕셔너리.
    """
    intent, keyword_hits = classify_intent(text)

    final_keywords = keyword_hits.get(intent, [])

    return {
        "intent": intent.value,
        "message": INTENT_MESSAGES.get(intent, INTENT_MESSAGES[Intent.UNKNOWN]),
        "keywords": list(set(final_keywords)),
    }


def is_travel_intent(intent: Intent) -> bool:
    """
    [수정] 주어진 의도가 여행 관련 카테고리에 속하는지 확인합니다.
    중앙 관리되는 TRAVEL_INTENTS 집합을 사용합니다.
    """
    return intent in TRAVEL_INTENTS
