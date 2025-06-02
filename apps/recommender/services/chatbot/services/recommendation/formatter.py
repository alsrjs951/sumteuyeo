def format_as_cards(items):
    return [{
        "title": item["title"],
        "contentid": item["contentid"],
        "category": f"{item['lclsSystm1']} > {item['lclsSystm2']} > {item['lclsSystm3']}",
        "overview": item["overview"][:200] + "...",
        "reason": ""
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