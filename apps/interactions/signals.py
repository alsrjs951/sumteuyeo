from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import ContentInteraction
from .tasks import cleanup_old_interactions
from users.services.preference_service import PreferenceService
from celery import shared_task

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
