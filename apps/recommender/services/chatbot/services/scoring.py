from config.ranking_config import RANKING_WEIGHTS

def score_item(item, user_profile, faiss_distance=None):
    score = 0.0
    if item.get("cat3") in user_profile.get("liked_cat3", []):
        score += RANKING_WEIGHTS["cat3_match"]
    if item.get("title") in user_profile.get("visited", []):
        score += RANKING_WEIGHTS["already_visited"]
    if user_profile.get("location") in item.get("overview", ""):
        score += RANKING_WEIGHTS["location_match"]
    if any(region in item.get("overview", "") for region in user_profile.get("preferred_regions", [])):
        score += RANKING_WEIGHTS["preferred_region_match"]
    if faiss_distance is not None:
        score -= faiss_distance * RANKING_WEIGHTS["faiss_distance_weight"]
    return score
