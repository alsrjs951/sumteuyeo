def format_as_cards(items):
    return [{
        "title": item["title"],
        "contentid": item["contentid"],
        "category": f"{item['cat1']} > {item['cat2']} > {item['cat3']}",
        "overview": item["overview"][:200] + "...",
        "reason": f"'{item['cat3']}' 관련 장소이고, 선호도 및 지역 기반 추천입니다."
    } for item in items]

'''
def generate_schedule(recommendations, days=2):
    schedule = {}
    per_day = max(1, len(recommendations) // days)
    for i in range(days):
        start = i * per_day
        end = start + per_day
        schedule[f"Day {i+1}"] = recommendations[start:end]
    return schedule
'''