from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import ContentInteraction
from .tasks import cleanup_old_interactions
from apps.users.services.preference_service import PreferenceService
from celery import shared_task
import logging
from django.core.cache import cache

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ContentInteraction)
def handle_interaction_update(sender, instance, **kwargs):
    if kwargs.get('created', False):
        cleanup_old_interactions.delay(instance.user_id)

    # 1. 조건 검증
    if instance.action_type not in PreferenceService.ACTION_WEIGHTS:
        return
    
    # 2. 트랜잭션 완료 보장
    transaction.on_commit(
        lambda: PreferenceService.delay_realtime_update(instance.user_id)
    )

@receiver(post_save, sender=ContentInteraction)
def clear_user_recommendation_cache(sender, instance, **kwargs):
    """사용자 상호작용 발생 시 추천 캐시 무효화"""
    try:
        user = instance.user
        if user.is_authenticated:
            # 캐시 키 패턴 생성 (예: "rec:42:m*")
            cache_pattern = f"rec:{user.id}:m*"
            
            # Redis 패턴 삭제
            deleted_count = cache.delete_pattern(cache_pattern)
            
            logger.info(
                f"사용자 {user.id} 캐시 무효화: {cache_pattern}, 삭제된 키 수: {deleted_count}"
            )
    except Exception as e:
        logger.error(f"캐시 삭제 실패: {str(e)}", exc_info=True)