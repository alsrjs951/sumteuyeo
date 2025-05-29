import pytest
from apps.recommender.services.chatbot.utils.filtering import analyze_user_input, is_travel_related

def test_recommend_tour():
    text = "서울 여행 코스 추천해줘"
    result = analyze_user_input(text)
    assert result["intent"] == "recommend_tour"
    assert "여행" in result["keywords"] or "추천" in result["keywords"]
    assert "추천" in result["message"]

def test_recommend_food():
    text = "제주도 맛집 알려줘"
    result = analyze_user_input(text)
    assert result["intent"] == "recommend_food"
    assert any(k in result["keywords"] for k in ["맛집", "음식"])
    assert "맛집" in result["message"]

def test_malicious_input():
    text = "너 바보야?"
    result = analyze_user_input(text)
    assert result["intent"] == "malicious"
    assert "도와드릴 수 있어요" in result["message"]

def test_unknown_intent():
    text = "날씨 어때?"
    result = analyze_user_input(text)
    assert result["intent"] == "unknown"
    assert "정확히 이해하지 못했어요" in result["message"]

def test_is_travel_related_true():
    text = "부산 여행지 추천해줘"
    assert is_travel_related(text) == True

def test_is_travel_related_false():
    text = "오늘 뉴스 뭐야?"
    assert is_travel_related(text) == False
