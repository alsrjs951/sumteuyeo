import numpy as np
from django.db import transaction
from django.utils import timezone
from users.models import UserPreferenceProfile, GlobalPreferenceProfile
import logging

logger = logging.getLogger(__name__)

class GlobalPreferenceService:
    TIME_DECAY_RATE = 0.01  # 시간 가중치 감쇠율 (일 단위)
    MIN_USERS = 10  # 최소 사용자 수 조건

    @classmethod
    def _calculate_decay_weight(cls, last_updated):
        """시간 감쇠 가중치 계산"""
        days_diff = (timezone.now() - last_updated).days
        return np.exp(-cls.TIME_DECAY_RATE * days_diff)

    @classmethod
    def _aggregate_vectors(cls, category_field):
        """벡터 집계 수행"""
        query = UserPreferenceProfile.objects.exclude(**{category_field: None})
        total_weight = 0.0
        sum_vector = np.zeros(484, dtype=np.float32)

        for profile in query.only(category_field, 'last_updated').iterator():
            vector = np.array(getattr(profile, category_field), dtype=np.float32)
            weight = cls._calculate_decay_weight(profile.last_updated)
            
            sum_vector += vector * weight
            total_weight += weight

        if total_weight < 1e-9 or len(query) < cls.MIN_USERS:
            return None
        normalized = sum_vector / total_weight
        if np.isnan(normalized).any():
            return None
            
        return normalized.tolist()

    @classmethod
    @transaction.atomic
    def update_global_profile(cls):
        try:
            global_profile, created = GlobalPreferenceProfile.objects.select_for_update().get_or_create(
                id=1,
                defaults={
                    'experience': np.zeros(484).tolist(),
                    'food': np.zeros(484).tolist()
                }
            )

            # 벡터 업데이트 로직
            update_fields = []
            for field in ['experience', 'food']:
                vector = cls._aggregate_vectors(field)
                if vector is not None or created:
                    setattr(global_profile, field, vector if vector else np.zeros(484))
                    update_fields.append(field)

            if update_fields:
                global_profile.save(update_fields=update_fields)

        except Exception as e:
            logger.error(f"초기화 실패: {str(e)}")
            raise
