import numpy as np
from django.utils import timezone
from apps.users.models import UserPreferenceProfile, GlobalPreferenceProfile
import logging
from django.db import transaction, DatabaseError

logger = logging.getLogger(__name__)

class GlobalPreferenceService:
    TIME_DECAY_RATE = 0.01  # 시간 가중치 감쇠율 (일 단위)
    MIN_USERS = 1  # 최소 사용자 수 조건
    VECTOR_DIM = 484  # 벡터 차원 상수화

    @classmethod
    def _calculate_decay_weight(cls, current_time, last_updated):
        """시간 감쇠 가중치 계산 (단일 시간 기준)"""
        days_diff = (current_time - last_updated).days
        return np.exp(-cls.TIME_DECAY_RATE * days_diff)

    @classmethod
    def _aggregate_vectors(cls, category_field, force=False):
        """벡터 집계 최적화 (쿼리 1회 실행 보장)"""
        try:
            # 단일 쿼리 실행으로 데이터 캐싱
            profiles = list(UserPreferenceProfile.objects
                .exclude(**{category_field: None})
                .only(category_field, 'last_updated', 'user_id')
                .iterator(chunk_size=1000))
            
            if not force and len(profiles) < cls.MIN_USERS:
                return None

            current_time = timezone.now()
            vectors = []
            weights = []

            # 벡터 사전 처리
            for profile in profiles:
                vector = np.array(getattr(profile, category_field), dtype=np.float32)
                if vector.shape != (cls.VECTOR_DIM,):
                    logger.warning(f"Invalid vector shape {vector.shape} for user {profile.user_id}")
                    continue
                
                weight = cls._calculate_decay_weight(current_time, profile.last_updated)
                vectors.append(vector)
                weights.append(weight)

            if not vectors:
                return None

            # 벡터 연산 일괄 처리
            weight_sum = np.sum(weights)
            if weight_sum < 1e-9:
                return None

            weighted_vectors = np.array(vectors) * np.array(weights)[:, None]
            sum_vector = np.sum(weighted_vectors, axis=0)
            normalized = sum_vector / weight_sum

            return normalized.tolist() if not np.isnan(normalized).any() else None

        except DatabaseError as e:
            logger.error(f"DB 오류 발생: {str(e)}", exc_info=True)
            raise

    @classmethod
    @transaction.atomic
    def update_global_profile(cls, force=False):
        """원자적 벡터 업데이트 (락 시간 최소화 버전)"""
        try:
            # 락 획득 시간 단축을 위한 사전 조건 검증
            if not force and not cls._has_min_users():
                logger.warning("최소 사용자 수 미달로 업데이트 중단")
                return False

            # 트랜잭션 시작
            global_profile, created = GlobalPreferenceProfile.objects.select_for_update(nowait=True).get_or_create(
                id=1,
                defaults={
                    'experience': np.zeros(cls.VECTOR_DIM).tolist(),
                    'food': np.zeros(cls.VECTOR_DIM).tolist()
                }
            )

            update_fields = []
            for field in ['experience', 'food']:
                vector = cls._aggregate_vectors(field, force=force)
                
                # NULL 값 방지 안전장치
                if vector is None:
                    if created:
                        vector = np.zeros(cls.VECTOR_DIM).tolist()
                    else:
                        continue
                
                # 차원 일치 검증 (치명적 오류 방지)
                if len(vector) != cls.VECTOR_DIM:
                    logger.error(f"Invalid aggregated vector length: {len(vector)}")
                    continue
                
                setattr(global_profile, field, vector)
                update_fields.append(field)

            if update_fields:
                global_profile.save(update_fields=update_fields)
                logger.info(f"글로벌 프로필 업데이트 완료: {', '.join(update_fields)}")
                return True
            return False

        except DatabaseError as e:
            logger.critical(f"글로벌 프로필 업데이트 실패: {str(e)}", exc_info=True)
            raise
        except ValueError as e:
            logger.error(f"벡터 처리 오류: {str(e)}")
            return False

    @classmethod
    def _has_min_users(cls):
        """카테고리별 최소 사용자 수 충족 여부 검증"""
        experience_count = UserPreferenceProfile.objects.exclude(experience=None).count()
        food_count = UserPreferenceProfile.objects.exclude(food=None).count()
        return min(experience_count, food_count) >= cls.MIN_USERS