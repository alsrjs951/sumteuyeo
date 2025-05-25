import re
from apps.recommender.services.chatbot.constants import FORBIDDEN_PATTERNS

def is_malicious(text):
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in FORBIDDEN_PATTERNS)

def is_travel_related(text):
    keywords = ["여행", "코스", "추천", "일정", "맛집", "가고 싶어", "명소"]
    return any(kw in text.lower() for kw in keywords)
