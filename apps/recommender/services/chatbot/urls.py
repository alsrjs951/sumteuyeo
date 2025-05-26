from django.urls import path
from .views import ChatbotAsyncView

urlpatterns = [
    path("chat/", ChatbotAsyncView.as_view(), name="chatbot_api"),
]
