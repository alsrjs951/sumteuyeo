# apps/users/urls.py

from django.urls import path
from . import views  # users 앱의 views.py 파일을 임포트합니다.

app_name = 'users_api' # URL 이름 충돌을 피하기 위해 앱 네임스페이스를 지정 (선택 사항이지만 권장)

urlpatterns = [
    # 회원가입 API 엔드포인트 URL
    # 예: POST 요청을 /api/auth/signup/ 으로 보내면 views.signup_api_view 함수가 처리
    path('signup/', views.signup_api_view, name='signup'),

    # 로그인 API 엔드포인트 URL
    # 예: POST 요청을 /api/auth/login/ 으로 보내면 views.login_api_view 함수가 처리
    path('login/', views.login_api_view, name='login'),

    # 로그아웃 API 엔드포인트 URL
    # 예: POST 요청을 /api/auth/logout/ 으로 보내면 views.logout_api_view 함수가 처리
    path('logout/', views.logout_api_view, name='logout'),
]