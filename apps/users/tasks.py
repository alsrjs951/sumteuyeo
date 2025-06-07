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
    try:
        success = global_preference_service.update_global_profile()
        if not success:
            raise Exception("Global profile update failed")  # 명시적 예외 발생
    except Exception as e:
        logger.critical(f"Critical failure: {str(e)}")  # 심각도 높은 로깅
        raise