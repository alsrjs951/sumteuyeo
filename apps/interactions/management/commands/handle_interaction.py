# handle_interaction.py
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.core.cache import cache
from apps.items.models import ContentDetailCommon
from apps.interactions.models import ContentInteraction
from apps.users.models import UserBookmark
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "CLI에서 다양한 콘텐츠 상호작용 기록을 처리하는 명령어"
    
    def add_arguments(self, parser):
        parser.add_argument('--user', type=int, required=True, help='사용자 ID (필수)')
        parser.add_argument('--content', type=int, required=True, help='콘텐츠 ID (필수)')
        parser.add_argument('--action', type=str, required=True,
                        choices=['click', 'bookmark', 'like', 'dislike', 'duration'],
                        help='액션 타입: click|bookmark|like|dislike|duration')
        parser.add_argument('--duration', type=float, help='체류 시간(초), duration 액션에서 필수')
        parser.add_argument('--toggle', action='store_true', help='북마크 토글 모드 활성화')


    def handle(self, *args, **options):
        User = get_user_model()
        
        try:
            user = User.objects.get(pk=options['user'])
            content = ContentDetailCommon.objects.get(contentid=options['content'])
            
            action_map = {
                'click': self.handle_click,
                'bookmark': self.handle_bookmark,
                'like': self.handle_rating,
                'dislike': self.handle_rating,
                'duration': self.handle_duration
            }
            
            action_handler = action_map[options['action']]
            action_handler(user, content, options)
            
            self.stdout.write(self.style.SUCCESS("상호작용 처리 완료"))
            
        except Exception as e:
            logger.error(f"상호작용 처리 실패: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"오류 발생: {str(e)}"))

    def handle_click(self, user, content, options):
        """클릭 이벤트 처리 (30분 내 중복 방지)"""
        cache_key = f'cli_click_{user.id}_{content.contentid}'
        if not cache.get(cache_key):
            ContentInteraction.objects.create(
                user=user,
                content=content,
                action_type='click'
            )
            cache.set(cache_key, True, 1800)

    def handle_bookmark(self, user, content, options):
        """북마크 토글 처리 (원자적 연산 보장)"""
        with transaction.atomic():
            bookmark = UserBookmark.objects.select_for_update().filter(
                user=user, 
                content=content
            ).first()
            
            if bookmark:
                bookmark.delete()
                ContentInteraction.objects.filter(
                    user=user,
                    content=content,
                    action_type='bookmark'
                ).delete()
            else:
                UserBookmark.objects.create(user=user, content=content)
                ContentInteraction.objects.update_or_create(
                    user=user,
                    content=content,
                    action_type='bookmark',
                    defaults={'active': True}
                )

    def handle_rating(self, user, content, options):
        """평점 처리 (좋아요/싫어요 상호배제)"""
        rating_type = options['action']
        with transaction.atomic():
            ContentInteraction.objects.filter(
                user=user,
                content=content,
                action_type__in=['like', 'dislike']
            ).delete()
            
            ContentInteraction.objects.create(
                user=user,
                content=content,
                action_type=rating_type
            )

    def handle_duration(self, user, content, options):
        """체류 시간 처리 (CLI 특화 구현)"""
        if not options.get('duration'):
            raise ValueError("체류 시간(duration) 파라미터 필수")
            
        ContentInteraction.objects.create(
            user=user,
            content=content,
            action_type='duration',
            duration=options['duration'],
            timestamp=timezone.now()
        )

# # 명령어 사용 예시
#
# 파라미터에 user 는 user_id 컬럼이고, content 는 contentid 컬럼입니다.
#
# # 클릭 이벤트 기록
# python manage.py handle_interaction \
#     --user=1 \
#     --content=123 \
#     --action=click
#
# # 북마크 토글
# python manage.py handle_interaction \
#     --user=1 \
#     --content=456 \
#     --action=bookmark \
#     --toggle
#
# # 체류 시간 기록 (60.5초)
# python manage.py handle_interaction \
#     --user=1 \
#     --content=789 \
#     --action=duration \
#     --duration=60.5
