from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db import transaction
from django.core.cache import cache
from datetime import timedelta
from apps.users.models import UserBookmark
from apps.items.models import ContentDetailCommon
from .models import ContentInteraction
import time
from apps.users.models import UserRating

class ContentClick(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        content = get_object_or_404(ContentDetailCommon, contentid=content_id)
        
        # 캐시 기반 중복 클릭 방지 (30분 유효)
        cache_key = f'click_{user.id}_{content.contentid}'
        if not cache.get(cache_key):
            cache.set(cache_key, True, timeout=1800)
            ContentInteraction.objects.create(
                user=user,
                content=content,
                action_type='click'
            )
            return Response(status=status.HTTP_201_CREATED)
        return Response(status=status.HTTP_200_OK)

class BookmarkToggle(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        content = get_object_or_404(ContentDetailCommon, contentid=content_id)

        with transaction.atomic():
            # Select for update로 동시성 문제 해결
            bookmark = UserBookmark.objects.select_for_update().filter(
                user=user,
                content=content
            ).first()

            if bookmark:
                # 북마크 제거
                bookmark.delete()
                ContentInteraction.objects.filter(
                    user=user,
                    content=content,
                    action_type='bookmark'
                ).delete()
                return Response({'status': 'removed'}, status=status.HTTP_200_OK)
            else:
                # 북마크 추가
                UserBookmark.objects.create(user=user, content=content)
                ContentInteraction.objects.update_or_create(
                    user=user,
                    content=content,
                    action_type='bookmark',
                    defaults={'active': True}
                )
                return Response({'status': 'added'}, status=status.HTTP_201_CREATED)

class ContentRating(APIView):
    permission_classes = [IsAuthenticated]
    VALID_RATINGS = ['like', 'dislike']

    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        rating_type = request.data.get('type')
        content = get_object_or_404(ContentDetailCommon, contentid=content_id)

        if rating_type not in self.VALID_RATINGS:
            return Response(
                {"error": "Invalid rating type"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            # 기존 평가 삭제
            ContentInteraction.objects.filter(
                user=user,
                content=content,
                action_type__in=self.VALID_RATINGS
            ).delete()

            # UserRating 기존 평가 삭제 및 새로 생성
            UserRating.objects.filter(
                user=user,
                content=content
            ).delete()
            UserRating.objects.create(
                user=user,
                content=content,
                rating_type=rating_type
            )

            # 새 평가 생성
            ContentInteraction.objects.create(
                user=user,
                content=content,
                action_type=rating_type
            )

        return Response(status=status.HTTP_201_CREATED)


class ContentDuration(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        content_id = request.data.get('content_id')
        content = get_object_or_404(ContentDetailCommon, contentid=content_id)
        
        # 세션 기반 체류 시간 계산
        session_key = f'content_{content.contentid}_duration'
        start_time = request.session.get(session_key)
        
        if not start_time:
            # 세션 시작 시간 기록
            request.session[session_key] = timezone.now().timestamp()
            return Response(status=status.HTTP_202_ACCEPTED)
        else:
            # 체류 시간 계산 및 저장
            end_time = timezone.now().timestamp()
            duration = end_time - start_time
            del request.session[session_key]
            
            ContentInteraction.objects.create(
                user=user,
                content=content,
                action_type='duration',
                duration=duration
            )
            return Response(status=status.HTTP_201_CREATED)
