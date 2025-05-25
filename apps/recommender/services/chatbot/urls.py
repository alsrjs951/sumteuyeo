from django.urls import path
from chatbot.views import ChatbotAsyncView

urlpatterns = [
    path("chat/", ChatbotAsyncView.as_view(), name="chatbot_api"),
]
