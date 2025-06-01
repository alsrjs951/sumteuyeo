weight_config = {
    "base": 1.0,
    "liked_category": 0.2,
    "visited_penalty": -0.3,
    "location_match": 0.1,
    "region_match": 0.15,
    "keyword_category_match": 0.3,
    "keyword_in_text": 0.2
}

def core_item_score(item, user_profile, intent=None, keywords=None):
    """
    하나의 관광 아이템에 대해 사용자 프로파일과 입력 의도/키워드 기반 점수를 계산합니다.
    """
    score = weight_config["base"]

    # 사용자 선호도 반영
    if item["lclsSystm3"] in user_profile["liked_lcls3"]:
        score += weight_config["liked_category"]
    if item["title"] in user_profile["visited"]:
        score += weight_config["visited_penalty"]
    if user_profile["location"] in item.get("overview", ""):
        score += weight_config["location_match"]
    if any(region in item.get("overview", "") for region in user_profile.get("preferred_regions", [])):
        score += weight_config["region_match"]

    # intent 기반 필터 (해당 intent가 아닌 경우 None 반환하여 제외)
    if intent == "recommend_food" and item.get("lclsSystm1") != "음식":
        return None
    if intent == "recommend_shopping" and item.get("lclsSystm2") != "쇼핑":
        return None
    if intent == "recommend_nature" and item.get("lclsSystm3") not in ["산", "바다", "공원", "계곡", "자연경관"]:
        return None

    # 키워드 기반 가중치
    if keywords:
        # 튜플 목록일 경우 문자열만 추출
        if isinstance(keywords[0], tuple):
            keywords = [kw[0] for kw in keywords]

        if item.get("lclsSystm3") in keywords:
            score += weight_config["keyword_category_match"]
        if any(kw in item.get("overview", "") for kw in keywords):
            score += weight_config["keyword_in_text"]

    return score
