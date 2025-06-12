from datetime import datetime, timedelta

# --- [수정] 새로운 가중치 설정 ---
# 각 항목의 중요도에 따라 가중치를 명확하게 분리하여 관리합니다.
weight_config = {
    "base": 0.1,  # 모든 후보가 받는 기본 점수
    "title_keyword": 0.8,  # 키워드가 '제목'에 포함될 때의 강력한 가중치
    "category_keyword": 0.5,  # 키워드가 '카테고리명'에 포함될 때
    "overview_keyword": 0.3,  # 키워드가 '개요'에 포함될 때
    "freshness_bonus": 0.2,  # 정보가 최신일 때
}


# --- 보조 함수들 (기존과 동일) ---
def code_to_name(code, cat_dict):
    return cat_dict.get(code, "")


def get_category_names(item, cat_dict):
    codes = [item.get(f"lclsSystm{i}", "") for i in range(1, 4)]
    return [name for name in [code_to_name(code, cat_dict) for code in codes] if name]


def expand_keywords_with_synonyms(keywords, synonym_dict):
    expanded_keywords = set(keywords)
    for kw in keywords:
        if kw in synonym_dict:
            expanded_keywords.update(synonym_dict[kw])
    return list(expanded_keywords)


# --- [수정] 핵심 점수 계산 함수 ---
def core_item_score(item, user_profile, intent=None, keywords=None, cat_dict=None):
    """
    [리팩토링] 필터링이 완료된 아이템에 대해, 사용자 쿼리 및 프로필과의
    '적합도 점수'를 계산하여 순위를 매기는 데 사용됩니다.
    """
    score = weight_config["base"]

    # --- 1. 키워드 적합도 점수 ---
    # 제목, 카테고리, 개요 순으로 가중치를 다르게 적용
    if keywords:
        item_title = item.get("title", "")
        item_overview = item.get("overview", "")
        category_names = get_category_names(item, cat_dict)
        category_text = " ".join(category_names)

        # 제목에 키워드가 하나라도 포함되면 큰 가산점 (가장 중요)
        if any(kw in item_title for kw in keywords):
            score += weight_config["title_keyword"]

        # 그 다음으로 카테고리명에 포함되는지 확인
        elif any(kw in category_text for kw in keywords):
            score += weight_config["category_keyword"]

        # 마지막으로 개요에 포함되는지 확인
        elif any(kw in item_overview for kw in keywords):
            score += weight_config["overview_keyword"]

    # --- 3. 신선도(Freshness) 점수 ---
    # 정보가 최근 1년 내에 수정되었다면 보너스 점수
    modified_time_str = item.get("modifiedtime", "20000101000000")
    try:
        modified_date = datetime.strptime(modified_time_str, "%Y%m%d%H%M%S")
        if modified_date > datetime.now() - timedelta(days=365):
            score += weight_config["freshness_bonus"]
    except ValueError:
        pass  # 날짜 형식이 잘못되어도 오류 없이 넘어감

    # --- 4. 불필요한 필터링 로직 제거 ---
    # 지역 및 카테고리 필터링은 get_recommendations에서 이미 수행했으므로,
    # 이 함수에서는 더 이상 후보를 탈락(return None)시키지 않습니다.

    return score


# --- [추가] '숨은 트렌디' 점수를 위한 가중치 설정 ---
hidden_trendy_weights = {
    "base": 1.0,
    "freshness_bonus": 0.5,  # 최근 1년 내 정보 수정 시 보너스
    "trendy_keyword_bonus": 0.8,  # '감성', '핫플' 등 트렌디 키워드 포함 시 보너스
    "quiet_category_bonus": 0.6,  # '북카페', '작은미술관' 등 한적한 카테고리 보너스
    "mainstream_penalty": -1.0,  # '대표 관광지', '필수 코스' 등 키워드 포함 시 페널티
    "crowded_category_penalty": -0.8  # '테마파크', '유명해수욕장' 등 붐비는 카테고리 페널티
}


# --- [추가] '숨은 트렌디' 점수 계산 함수 ---
def calculate_hidden_trendy_score(item, cat_dict):
    """
    '숨은 트렌디' 점수를 계산합니다. 높을수록 한적하고 트렌디한 곳입니다.
    """
    score = hidden_trendy_weights["base"]

    # 1. '트렌디함' 점수 (보너스)
    # - 최신성: 정보가 최근 1년 내에 수정되었다면 보너스
    modified_time_str = item.get("modifiedtime", "20000101000000")
    try:
        if datetime.strptime(modified_time_str, "%Y%m%d%H%M%S") > datetime.now() - timedelta(days=365):
            score += hidden_trendy_weights["freshness_bonus"]
    except ValueError:
        pass

    # - 트렌디 키워드: 제목이나 개요에 특정 키워드가 있으면 보너스
    trendy_keywords = [
        # 분위기 및 감성
        '감성', '아늑한', '조용한 카페', '힙한', '분위기 좋은', '고즈넉한',
        '인스타그래머블', '갬성', '빈티지', '레트로', '모던한', '이국적인',
        '뷰맛집', '오션뷰', '마운틴뷰', '리버뷰',

        # 최신 유행어 및 핫플
        '성지', '인생샷', '포토존', '리단길', '힙지로',

        # 장소 종류 및 컨셉
        '독립서점', 'LP바', '공방', '소품샵', '편집샵', '전시', '갤러리',
        '복합문화공간', '루프탑', '테라스', '북카페', '디저트카페', '베이커리카페',
        '와인바', '칵테일바', '브런치', '비건', '오마카세', '파인다이닝',

        # 장소 묘사
        '골목', '작은', '숨은', '로컬', '현지인 맛집', '나만 아는', '예쁜', '아기자기한',
        '오래된', '노포',

        # 특별한 경험
        '원데이클래스', '플리마켓', '워크샵', '팝업스토어', '팝업'
    ]
    item_text = item.get("title", "") + item.get("overview", "")
    if any(kw in item_text for kw in trendy_keywords):
        score += hidden_trendy_weights["trendy_keyword_bonus"]

    # 2. '숨겨짐'과 '한적함' 점수 (보너스 및 페널티)
    category_names = get_category_names(item, cat_dict)  # 기존 함수 재사용
    category_text = " ".join(category_names)

    # - 한적한 카테고리 보너스
    quiet_categories = [
        # 자연과 사색
        '수목원', '자연휴양림', '정원', '식물원', '사찰', '템플스테이',
        '삼림욕장', '치유의 숲', '생태공원', '다원', '농장', '목장',

        # 조용한 문화/예술
        '작은미술관', '미술관', '독립서점', '북카페', '갤러리', '기념관',
        '박물관', '문학관', '전통찻집', '공방',

        # 역사와 전통
        '고택', '서원', '향교', '종택', '민속마을', '성지', '유적', '사적'
    ]

    if any(cat in category_text for cat in quiet_categories):
        score += hidden_trendy_weights["quiet_category_bonus"]

    # - 붐비는 카테고리 페널티
    # score.py의 calculate_hidden_trendy_score 함수 안에 이 리스트를 사용하세요.

    crowded_categories = [
        # 기존 리스트
        '테마파크', '놀이공원', '유명해수욕장', '대형쇼핑몰', '아울렛',

        # 대규모 상업/문화 시설
        '백화점', '대형마트', '면세점', '워터파크', '아쿠아리움',
        '전망대', '대형공연장', '컨벤션센터', '경기장', '카지노',

        # 교통 허브 및 대형 시장
        '종합버스터미널', '기차역', 'KTX역', '공항',
        '대형시장', '야시장', '수산시장'
    ]

    # 중복 제거 및 최종 리스트화
    crowded_categories = list(set(crowded_categories))
    if any(cat in category_text for cat in crowded_categories):
        score += hidden_trendy_weights["crowded_category_penalty"]

    # - 주류/인기 관광지 키워드 페널티
    mainstream_keywords = [
        # 기존 리스트
        '대표 관광지', '필수 코스', '유명한', '모두가 아는', '랜드마크',

        # 인기도 및 대중성 표현
        '인기 명소', '인기있는', '핫플레이스', '핫플', '최고의', '명소',
        '사람들이 많이 찾는', '누구나 가는', '국민관광지',

        # 추천 및 권유 표현
        '꼭 가봐야 할', '놓치지 말아야 할', '필수 방문', '강력 추천', '추천 코스',

        # 미디어 노출 및 인증 관련
        'TV에 나온', '방송에 나온', '드라마 촬영지', '영화 촬영지',
        '인증샷', '인증샷 명소', '100선'  # 예: 한국관광 100선
    ]
    if any(kw in item_text for kw in mainstream_keywords):
        score += hidden_trendy_weights["mainstream_penalty"]

    return score
