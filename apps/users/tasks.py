# tasks.py
import logging
from celery import shared_task
from django.core.cache import cache
from django.utils import timezone
from apps.users.services.global_preference_service import GlobalPreferenceService  # 서비스 클래스 임포트 방식 변경
from apps.users.services.preference_service import PreferenceService
from apps.users.models import User
from django.db import transaction
from django.db.utils import DatabaseError

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    name='global_profile.update',
    queue='batch',
    priority=5,
    max_retries=3,
    autoretry_for=(DatabaseError, ValueError),  # 구체적 예외로 제한
    retry_backoff=120,  # 백오프 시간 증가
    retry_backoff_max=900,
    soft_time_limit=600,
    hard_time_limit=650,
    ignore_result=True  # 결과 저장 비활성화
)
def update_global_profile_task(self, force=False):
    try:
        logger.info(f"[GLOBAL] 강제 모드: {force}, 시도 횟수: {self.request.retries}")
        cache_key = f"global_update_lock"
        
        # 분산 락 메커니즘 추가
        with cache.lock(cache_key, timeout=700):
            success = GlobalPreferenceService().update_global_profile(force=force)
            
            if not success:
                logger.warning("서비스 레이어에서 실패 반환")
                if self.request.retries >= self.max_retries:
                    logger.error(f"[GLOBAL] 최대 재시도 횟수 초과: {self.request.retries}")
                raise self.retry(countdown=300)  # 5분 대기 후 재시도
                
            cache.delete("global_profile_cache")  # 캐시 무효화
            return {'status': 'success', 'timestamp': timezone.now().isoformat()}
    
    except Exception as e:
        logger.critical(f"[GLOBAL] 치명적 오류: {str(e)}", exc_info=True)
        raise



@shared_task(
    bind=True, 
    queue='realtime', 
    priority=6,
    max_retries=3,
    autoretry_for=(DatabaseError,), 
    retry_backoff=60,
    retry_jitter=True,  # 재시도 시간에 랜덤성 추가
    acks_late=True  # 작업 손실 방지
)
def update_user_preference_task(self, user_id):
    try:
        logger.debug(f"[USER {user_id}] 프로필 업데이트 시작")
        
        # 사용자 존재 여부 사전 확인
        if not User.objects.filter(id=user_id).exists():
            logger.error(f"[USER {user_id}] 존재하지 않는 사용자")
            return {'status': 'skipped', 'reason': 'user_not_found'}
            
        with transaction.atomic():
            user = User.objects.select_for_update().get(id=user_id)
            PreferenceService.update_user_preference(user)
            
        cache.delete(f"user_pref_{user_id}")  # 사용자 캐시 무효화
        logger.info(f"[USER {user_id}] 업데이트 성공")
        return {'status': 'success'}
    
    except DatabaseError as e:
        logger.warning(f"[USER {user_id}] DB 오류: {str(e)}")
        self.retry(exc=e, countdown=2 ** self.request.retries)
    
    except Exception as e:
        logger.error(f"[USER {user_id}] 예상치 못한 오류: {str(e)}")
        raise
