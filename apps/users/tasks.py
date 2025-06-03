from sumteuyeo.celery import app
from .services import global_preference_service
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@app.task(
    bind=True,
    queue='batch',
    priority=5,
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=600,
    retry_backoff_max=1800
)
def update_global_profile_task(self):
    """전역 프로필 주기적 업데이트 작업"""
    try:
        success = global_preference_service.update_global_profile()
        if not success:
            self.retry(countdown=600)
        return {"status": "success", "timestamp": timezone.now().isoformat()}
    except Exception as e:
        logger.error(f"Global profile task failed: {str(e)}", exc_info=True)
        raise self.retry(exc=e, max_retries=3)