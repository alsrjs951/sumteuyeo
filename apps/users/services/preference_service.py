import numpy as np
from django.db import transaction, DatabaseError
from django.utils import timezone
from django.core.exceptions import ValidationError
from apps.users.models import UserPreferenceProfile
from apps.interactions.models import ContentInteraction
from apps.recommender.models import ContentFeature
from apps.items.models import ContentDetailCommon
from celery import shared_task
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger(__name__)
User = get_user_model()

# 상수 정의
VECTOR_DIM = 484
CATEGORY_MAP = {
    'EX': 'experience', 'HS': 'experience', 'LS': 'experience',
    'NA': 'experience', 'SH': 'experience', 'VE': 'experience', 'FD': 'food'
}
DISLIKE_IMPACT = {'experience': 1.0, 'food': 0.7}

ACTION_WEIGHTS = {
    'click': 0.1, 'like': 0.8, 'dislike': 0.6, 
    'bookmark': 1.0, 'duration': 0.2
}

class PreferenceService:
    DECAY_RATE = 0.05

    ACTION_WEIGHTS = {
        'click': 0.1, 'like': 0.8, 'dislike': 0.6, 
        'bookmark': 1.0, 'duration': 0.2
    }

    @staticmethod
    def _validate_vector(vector):
        """벡터 차원 검증"""
        if len(vector) != VECTOR_DIM:
            raise ValidationError(f"벡터 차원 오류: {len(vector)} (필요: {VECTOR_DIM})")
        return vector

    @staticmethod
    def _normalize_vector(vector):
        norm = np.linalg.norm(vector)
        if norm < 1e-4:  # 기존 1e-8 → 1e-4로 완화 (소수점 4자리까지 허용)
            logger.warning(f"작은 노름 값: {norm}")
            return np.zeros_like(vector)
        return (vector / norm).astype(np.float32)
    
    @staticmethod
    def calculate_user_weight(interaction_count: int) -> float:
        if interaction_count <= 0:
            return 0.0
            
        max_count = 1000
        max_weight = 0.9  # 10% 글로벌 벡터 보존
        
        raw_weight = np.log1p(interaction_count) / np.log1p(max_count)
        return min(raw_weight, max_weight)  # 0.9 상한선 적용

    @classmethod
    def _process_interactions(cls, user):
        """상호작용-특징벡터 정확한 매핑 구현"""
        interactions = list(
            ContentInteraction.objects
            .filter(user=user)
            .select_related('content__feature')  # content.detail 사전 로드
            .only('action_type', 'timestamp', 'duration', 'content_id')
        )
        
        # ContentDetailCommon.contentid 추출
        contentids = [interaction.content.contentid for interaction in interactions]
        
        # ContentFeature 조회 (detail__contentid 사용)
        # 수정 코드: 프리페치 데이터 활용
        content_map = {
            inter.content.contentid: inter.content.feature
            for inter in interactions
            if inter.content.feature is not None
            and inter.content.feature.feature_vector is not None
        }

        
        logger.info(f"[DEBUG] ContentIDs: {contentids}")
        logger.info(f"[DEBUG] FeatureMap Keys: {list(content_map.keys())}")
        return interactions, content_map



    @classmethod
    def _calculate_time_weights(cls, interactions):
        """시간 가중치 벡터화 계산"""
        now = timezone.now()
        time_deltas = np.array([(now - i.timestamp).total_seconds() for i in interactions])
        return np.exp(-cls.DECAY_RATE * time_deltas / 86400)

    @classmethod
    @transaction.atomic
    def update_user_preference(cls, user):
        """원자적 프로필 업데이트 (pgvector 최적화)"""
        try:
            # 프로필 안전 생성 및 락 획득
            profile, created = UserPreferenceProfile.objects.select_for_update().get_or_create(
                user=user,
                defaults={
                    'experience': np.zeros(VECTOR_DIM).tolist(),
                    'food': np.zeros(VECTOR_DIM).tolist()
                }
            )
            
            interactions, content_map = cls._process_interactions(user)
            time_weights = cls._calculate_time_weights(interactions)
            
            # 가중치 계산
            action_weights = np.array([ACTION_WEIGHTS[i.action_type] for i in interactions])
            duration_weights = np.array([
                np.log1p(i.duration/60) if i.duration and i.action_type == 'duration' else 1.0 
                for i in interactions
            ])
            total_weights = action_weights * duration_weights * time_weights

            # 벡터 누적
            vectors = {'experience': np.zeros(VECTOR_DIM), 'food': np.zeros(VECTOR_DIM)}
            for idx, interaction in enumerate(interactions):
                contentid = interaction.content.contentid
                if (cf := content_map.get(contentid)) is None:
                    logger.warning(f"특징 벡터 없음: 콘텐츠 {contentid}")
                    continue

                lclssystm1 = cf.detail.lclssystm1
                category = CATEGORY_MAP.get(lclssystm1, 'experience')
                
                # 특징 벡터 강제 1D 변환
                raw_vector = np.array(cf.feature_vector, dtype=np.float32).flatten()
                
                # 차원 검증 (반드시 필요)
                if raw_vector.shape != (VECTOR_DIM,):
                    logger.error(f"잘못된 벡터 차원 {raw_vector.shape} (콘텐츠 {contentid})")
                    continue
                
                # 가중치 분해 및 적용
                text_part = raw_vector[:384] * 0.6
                cat_part = raw_vector[384:] * 1.4
                
                if interaction.action_type == 'dislike':
                    cat_part *= -DISLIKE_IMPACT.get(category, 1.0)
                
                vectors[category] += np.concatenate([text_part, cat_part]) * total_weights[idx]

            # 벡터 저장
            update_fields = []
            for category, vector in vectors.items():
                try:
                    validated = cls._validate_vector(vector)
                    normalized = cls._normalize_vector(validated)
                    setattr(profile, category, normalized.tolist())
                    update_fields.append(category)
                except ValidationError as e:
                    logger.error(f"벡터 저장 실패 ({category}): {str(e)}")
                    continue

            if update_fields:
                profile.save(update_fields=update_fields + ['last_updated'])
                logger.info(f"사용자 {user.id} {len(update_fields)}개 벡터 갱신")
            
            return True

        except DatabaseError as e:
            logger.critical(f"DB 오류 ({user.id}): {str(e)}")
            raise
        except Exception as e:
            logger.error(f"예상치 못한 오류 ({user.id}): {str(e)}")
            raise

    @shared_task(
        bind=True, 
        queue='realtime', 
        priority=9, 
        max_retries=3,
        autoretry_for=(DatabaseError,),
        retry_backoff=30
    )
    def delay_realtime_update(self, user_id):
        """Celery 실시간 업데이트 태스크"""
        try:
            user = User.objects.get(pk=user_id)
            with transaction.atomic():
                PreferenceService.update_user_preference(user)
            return {'status': 'success', 'user_id': user_id}
        
        except User.DoesNotExist as e:
            logger.error(f"사용자 없음: {user_id}")
            raise self.retry(exc=e, countdown=60)
        
        except DatabaseError as e:
            logger.warning(f"DB 오류 재시도: {user_id}")
            raise self.retry(exc=e, countdown=2 ** self.request.retries)
        
        except Exception as e:
            logger.critical(f"치명적 오류: {user_id} - {str(e)}")
            self.retry(exc=e, countdown=2 ** self.request.retries)
