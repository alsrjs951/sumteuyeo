from celery import shared_task
from django.conf import settings
from .models import ContentInteraction

@shared_task(queue='maintenance')
def cleanup_old_interactions(user_id):
    current_count = ContentInteraction.objects.filter(user_id=user_id).count()
    
    if current_count > settings.USER_INTERACTION_LIMIT:
        excess = current_count - settings.USER_INTERACTION_LIMIT
        oldest_ids = ContentInteraction.objects.filter(user_id=user_id) \
            .order_by('timestamp') \
            .values_list('id', flat=True)[:excess]
            
        ContentInteraction.objects.filter(id__in=list(oldest_ids)).delete()
