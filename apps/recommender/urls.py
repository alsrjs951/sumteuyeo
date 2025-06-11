from django.urls import path
from . import views
from .views import MainRecommendationAPI

app_name = 'recommender_api'

urlpatterns = [
    # 메인 화면 콘텐츠 추천 API 엔드포인트
    path('recommendations/main/', MainRecommendationAPI.as_view(), name='main-recommendations'),
]