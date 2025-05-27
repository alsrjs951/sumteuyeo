from ..utils.embedding import model, faiss_index, get_spot_data
from asgiref.sync import sync_to_async

spot_data = get_spot_data()

def get_user_profile(user_id):
    return {
        "liked_cat3": ["한식", "자연경관"],
        "visited": ["서울타워"],
        "location": "서울",
        "preferred_regions": ["서울", "경기도"]
    }

@sync_to_async
def get_recommendations(query, user_profile, top_n=5):
    query_vec = model.encode([query])
    D, I = faiss_index.search(query_vec, top_n * 5)
    scored_results = []
    for idx in I[0]:
        item = spot_data[idx]
        score = 1.0
        if item["cat3"] in user_profile["liked_cat3"]:
            score += 0.2
        if item["title"] in user_profile["visited"]:
            score -= 0.3
        if user_profile["location"] in item.get("overview", ""):
            score += 0.1
        if any(region in item.get("overview", "") for region in user_profile.get("preferred_regions", [])):
            score += 0.15
        scored_results.append((item, score))
    ranked = sorted(scored_results, key=lambda x: -x[1])[:top_n]
    return [item for item, score in ranked]

def format_as_cards(items):
    return [{
        "title": item["title"],
        "contentid": item["contentid"],
        "category": f"{item['cat1']} > {item['cat2']} > {item['cat3']}",
        "overview": item["overview"][:200] + "...",
        "reason": f"'{item['cat3']}' 관련 장소이고, 선호도 및 지역 기반 추천입니다."
    } for item in items]

def generate_schedule(recommendations, days=2):
    schedule = {}
    per_day = max(1, len(recommendations) // days)
    for i in range(days):
        start = i * per_day
        end = start + per_day
        schedule[f"Day {i+1}"] = recommendations[start:end]
    return schedule