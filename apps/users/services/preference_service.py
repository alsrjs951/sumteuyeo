import numpy as np
import math
from sklearn.preprocessing import normalize
from django.db import transaction, DatabaseError
from django.utils import timezone
from apps.users.models import UserPreferenceProfile
from apps.interactions.models import ContentInteraction
from apps.recommender.models import ContentFeature
from celery import shared_task
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

CATEGORY_MAP = {
    'EX': 'experience',     # 체험관광+역사+레저+자연+쇼핑+문화
    'HS': 'experience',
    'LS': 'experience',
    'NA': 'experience',
    'SH': 'experience',
    'VE': 'experience',
    'FD': 'food',           # 음식
}

# 카테고리별 부정 영향력 가중치
DISLIKE_IMPACT = {
    'experience': 1.0,
    'food': 0.7
}

class PreferenceService:

    ACTION_WEIGHTS = {
        'click': 0.1,
        'like': 0.8,
        'dislike': 0.6,
        'bookmark': 1.0,
        'duration': 0.2,
    }

    @staticmethod
    def calculate_user_weight(user_id: int) -> float:
        """상호작용 빈도 기반 개인 가중치 계산"""
        interaction_count = ContentInteraction.objects.filter(user_id=user_id).count()
        
        # 상호작용 100회 이상 → 90% 개인 가중치
        if interaction_count >= 100:
            return 0.9
        # 50~99회 → 80%
        elif interaction_count >= 50:
            return 0.8
        # 10~49회 → 70%
        elif interaction_count >= 10:
            return 0.7
        # 10회 미만 → 50%
        else:
            return 0.5
    
    DECAY_RATE = 0.05  # 시간 감쇠율 (값이 클수록 최근 데이터 강조)

    @staticmethod
    @transaction.atomic
    def update_user_preference(user):
        profile = UserPreferenceProfile.objects.select_for_update().get(user=user)
        updated_vectors = {key: np.zeros(484, dtype=np.float32) for key in CATEGORY_MAP.values()}
        
        # 프리페치 최적화 (2개 쿼리로 처리)
        interactions = (
            ContentInteraction.objects
            .filter(user=user)
            .only('action_type', 'timestamp', 'duration', 'content_id')
        )
        content_ids = [i.content_id for i in interactions]
        
        # 벌크 조회 및 매핑 테이블 생성
        content_map = {
            cf.content_id: cf 
            for cf in ContentFeature.objects.filter(content_id__in=content_ids)
                .select_related('detail')
                .only('feature_vector', 'detail__lclsSystm1')
        }

        # 시간 감쇠 계산 벡터화
        now = timezone.now()
        time_deltas = np.array([(now - i.timestamp).total_seconds() for i in interactions])
        time_weights = np.exp(-PreferenceService.DECAY_RATE * time_deltas / 86400)
        
        # 가중치 계산 벡터화
        action_weights = np.array([
            PreferenceService.ACTION_WEIGHTS[i.action_type] 
            for i in interactions
        ])
        duration_weights = np.array([
            np.log1p(i.duration/60) if i.duration and i.action_type == 'duration' else 1.0
            for i in interactions
        ])
        total_weights = action_weights * duration_weights * time_weights

        # 벡터 누적 프로세스 (개선된 버전)
        for idx, interaction in enumerate(interactions):
            if (cf := content_map.get(interaction.content_id)) is None:
                continue
                
            category = CATEGORY_MAP.get(cf.detail.lclsSystm1, 'experience')
            raw_vector = np.array(cf.feature_vector, dtype=np.float32)
            
            # 벡터 분해 및 가중치 적용
            text_part = raw_vector[:384] * 0.6  # 텍스트 가중치 60%
            cat_part = raw_vector[384:] * 1.4    # 카테고리 가중치 140%
            
            # 부정 반응 처리 (카테고리 부분에만 적용)
            if interaction.action_type == 'dislike':
                cat_part *= -DISLIKE_IMPACT.get(category, 1.0)
                
            enhanced_vector = np.concatenate([text_part, cat_part])
            updated_vectors[category] += enhanced_vector * total_weights[idx]
        
        # 벡터 정규화 병렬 처리
        for category, vector in updated_vectors.items():
            norm = np.linalg.norm(vector)
            if norm > 1e-8 and not np.isnan(norm):
                normalized = normalize([vector])[0].tolist()
            else:
                normalized = vector.tolist()
            setattr(profile, category, normalized)
        
        profile.save(update_fields=['experience', 'food', 'last_updated'])

    @shared_task(bind=True, queue='realtime', priority=9, max_retries=3)
    def delay_realtime_update(self, user_id):
        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
            with transaction.atomic():
                PreferenceService.update_user_preference(user)
        except User.DoesNotExist as e:
            logger.error(f"User {user_id} does not exist: {str(e)}")
        except DatabaseError as e:
            self.retry(exc=e, countdown=2 ** self.request.retries)
        except Exception as e:
            logger.error(f"Critical error: {str(e)}")
            raise
