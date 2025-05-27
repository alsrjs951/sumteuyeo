def score_item(item, user_profile):
    score = 1.0
    if item["cat3"] in user_profile["liked_cat3"]:
        score += 0.3
    if user_profile["location"] in item.get("overview", ""):
        score += 0.2
    if item["title"] in user_profile["visited"]:
        score -= 0.5
    if any(region in item.get("overview", "") for region in user_profile["preferred_regions"]):
        score += 0.25

    # 가중치 기반 점수 정규화
    return round(score, 3)