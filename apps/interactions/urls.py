from django.urls import path
from . import views

urlpatterns = [
    path('interaction/click/', views.ContentClick.as_view()),
    path('interaction/bookmark/', views.BookmarkToggle.as_view()),
    path('interaction/rating/', views.ContentRating.as_view()),
    path('interaction/duration/', views.ContentDuration.as_view()),
]
