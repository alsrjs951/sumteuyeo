weight_config = {
    "base": 1.0,
    "liked_category": 0.5,   # 실험적으로 더 높임
    "visited_penalty": -0.5, # 방문한 곳은 더 강하게 제외
    "location_match": 0.4,
    "region_match": 0.4,
    "keyword_category_match": 0.8,
    "keyword_in_text": 0.7
}

def code_to_name(code, cat_dict):
    return cat_dict.get(code, "")
def get_category_names(item, cat_dict):
    codes = []
    if "lclsSystm1" in item:
        codes.append(item["lclsSystm1"])
    if "lclsSystm2" in item:
        codes.append(item["lclsSystm2"])
    if "lclsSystm3" in item:
        codes.append(item["lclsSystm3"])
    names = [code_to_name(code, cat_dict) for code in codes]
    return [name for name in names if name]

#키워드 확장 함수
def expand_keywords_with_synonyms(keywords, synonym_dict):
    expanded_keywords = set(keywords)
    for kw in keywords:
        if kw in synonym_dict:
            expanded_keywords.update(synonym_dict[kw])
    return list(expanded_keywords)

def core_item_score(item, user_profile, intent=None, keywords=None,  cat_dict=None):
    """
    하나의 관광 아이템에 대해 사용자 프로파일과 입력 의도/키워드 기반 점수를 계산합니다.
    """
    score = weight_config["base"]

    # 사용자 선호도 반영
    category_names = get_category_names(item, cat_dict)
    for name in category_names:
        if name in user_profile.get("liked_lcls", []):
            score += weight_config["liked_category"]
    if item["title"] in user_profile.get("visited", []):
        score += weight_config["visited_penalty"]
    if user_profile.get("location", "") in item.get("overview", ""):
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
        if isinstance(keywords[0], tuple):
            keywords = [kw[0] for kw in keywords]
        # 코드 변환해서 실제 이름 리스트 생성
        # overview, title, 카테고리 이름에서 키워드 매칭
        if any(kw in item.get("overview", "") for kw in keywords):
            score += weight_config["keyword_in_text"]
        if any(kw in item.get("title", "") for kw in keywords):
            score += weight_config["keyword_in_text"]
        if any(kw in " ".join(category_names) for kw in keywords):
            score += weight_config["keyword_category_match"]
    return score

