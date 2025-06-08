from django.urls import path
from . import views

app_name = 'items_api'

urlpatterns = [
    # 프론트엔드 JavaScript에서 호출할 주변 관광지 "목록" API 엔드포인트
    path('receive-location/', views.receive_location, name='receive_location_list'),  # 이름 변경 권장

    # 새로운 관광지 "상세 정보" API 엔드포인트
    # 예: /api/recommender/place-detail/12345/ (프로젝트의 urls.py 설정에 따라 /api/recommender/ 는 달라질 수 있음)
    path('place-detail/<int:content_id>/', views.get_place_detail_view, name='get_place_detail'),

    # HTML 템플릿을 렌더링하는 뷰 (이전과 동일)
    path('get-location-page/', views.location_page_view, name='location_page'),
]