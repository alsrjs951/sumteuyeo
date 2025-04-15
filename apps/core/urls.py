from django.urls import path
from . import views

app_name = 'core'
urlpatterns = [
    path('', views.main_page_view, name='main_page'),
]