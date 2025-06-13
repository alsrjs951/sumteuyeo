from django.urls import path
from .views import ChatbotAsyncView, TripPlannerView

urlpatterns = [
    path("chat/", ChatbotAsyncView.as_view(), name="chatbot_api"),
    path('trip/item/', TripPlannerView.as_view(), name='trip_item'), # ⭐️ 장바구니 아이템 추가/삭제
    path('trip/itinerary/', TripPlannerView.as_view(), name='trip_itinerary') # ⭐️ 최종 일정 생성
]
