from django.urls import path
from . import views

urlpatterns = [
    # 프론트엔드 JavaScript에서 호출할 API 엔드포인트
    path('receive-location/', views.receive_location, name='receive_location'),
    # HTML 템플릿을 렌더링하는 뷰 (예시)
    path('get-location-page/', views.location_page_view, name='location_page'),
]