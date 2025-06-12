from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    path('', views.main_page_view, name='main_page'),
    # '내 정보' 페이지를 위한 URL
    path('my-info.html', views.my_info_view, name='my-info'),

    # '설문조사' 페이지를 위한 URL
    path('survey.html', views.survey_view, name='survey'),

    # '관광정보 수정요청' 페이지를 위한 URL
    path('mod-request.html', views.mod_request_view, name='mod-request'),
]
