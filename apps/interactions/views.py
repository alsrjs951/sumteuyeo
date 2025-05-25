from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import ContentInteraction
import time
from django.utils import timezone
from datetime import timedelta

class ContentClick(APIView):
    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        
        # 세션당 중복 클릭 방지 (30분 유효)
        if not ContentInteraction.objects.filter(
            user=user, 
            content_id=content_id,
            action_type='click',
            timestamp__gte=timezone.now()-timedelta(minutes=30)
        ).exists():
            ContentInteraction.objects.create(
                user=user,
                content_id=content_id,
                action_type='click'
            )
        return Response(status=status.HTTP_201_CREATED)

class BookmarkToggle(APIView):
    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        obj, created = ContentInteraction.objects.update_or_create(
            user=user,
            content_id=content_id,
            action_type='bookmark',
            defaults={'active': not ContentInteraction.objects.filter(
                user=user,
                content_id=content_id,
                action_type='bookmark'
            ).exists()}
        )
        return Response({'status': 'added' if obj.active else 'removed'})

class ContentRating(APIView):
    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        rating_type = request.data.get('type')  # like/dislike
        
        # 기존 평가 삭제
        ContentInteraction.objects.filter(
            user=user,
            content_id=content_id,
            action_type__in=['like', 'dislike']
        ).delete()
        
        ContentInteraction.objects.create(
            user=user,
            content_id=content_id,
            action_type=rating_type
        )
        return Response(status=status.HTTP_201_CREATED)

class ContentDuration(APIView):
    def post(self, request):
        start = request.data.get('start')  # 프론트에서 전달한 타임스탬프
        end = request.data.get('end')
        duration = end - start
        
        ContentInteraction.objects.create(
            user=request.user,
            content_id=request.data.get('content_id'),
            action_type='duration',
            duration=duration
        )
        return Response(status=status.HTTP_201_CREATED)
