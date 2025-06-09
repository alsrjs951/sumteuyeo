from django.urls import path
from . import views

urlpatterns = [
    path('click/', views.ContentClick.as_view()),
    path('bookmark/', views.BookmarkToggle.as_view()),
    path('rating/', views.ContentRating.as_view()),
    path('duration/', views.ContentDuration.as_view()),
]
