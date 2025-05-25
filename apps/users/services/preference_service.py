import numpy as np
import math
from sklearn.preprocessing import normalize
from django.db import transaction
from django.utils import timezone
from users.models import UserPreferenceProfile
from interactions.models import ContentInteraction
from recommender.models import ContentFeature

CATEGORY_MAP = {
    'AC': 'accommodation',  # 숙박
    'EV': 'festival_event', # 축제/공연/행사
    'EX': 'experience',     # 체험관광+역사+레저+자연+쇼핑+문화
    'HS': 'experience',
    'LS': 'experience',
    'NA': 'experience',
    'SH': 'experience',
    'VE': 'experience',
    'FD': 'food',           # 음식
}

class PreferenceService:

    ACTION_WEIGHTS = {
        'click': 0.1,
        'like': 0.8,
        'dislike': 0.6,
        'bookmark': 1.0,
        'duration': 0.2,
    }
    
    DECAY_RATE = 0.05  # 시간 감쇠율 (값이 클수록 최근 데이터 강조)

    @staticmethod
    @transaction.atomic
    def update_user_preference(user):
        profile, _ = UserPreferenceProfile.objects.get_or_create(user=user)
        updated_vectors = {key: np.zeros(484, dtype=np.float32) for key in CATEGORY_MAP.values()}
        
        interactions = ContentInteraction.objects.filter(user=user)
        
        for interaction in interactions:
            # 시간 감쇠 계산 (최근일수록 가중치 ↑)
            delta = timezone.now() - interaction.timestamp
            days_ago = delta.total_seconds() / 86400  # 일(day) 단위
            time_weight = math.exp(-PreferenceService.DECAY_RATE * days_ago)
            
            try:
                content = ContentFeature.objects.get(content_id=interaction.content_id)
                main_cat_code = content.detail.lclsSystm1
                main_cat_field = CATEGORY_MAP.get(main_cat_code, 'experience')
            except ContentFeature.DoesNotExist:
                continue

            # 액션 가중치 + 체류시간 가중치 + 시간 가중치 결합
            base_weight = PreferenceService.ACTION_WEIGHTS.get(interaction.action_type, 0.1)
            if interaction.action_type == 'dislike':
                base_weight *= -1  # 부정적 피드백 반영
            
            duration_weight = 1.0
            
            if interaction.action_type == 'duration' and interaction.duration and base_weight > 0:
                duration_weight += np.log1p(interaction.duration / 60)
                
            total_weight = base_weight * duration_weight * time_weight
            
            # 벡터 누적
            content_vector = np.array(content.feature_vector, dtype=np.float32)
            updated_vectors[main_cat_field] += content_vector * total_weight

        # 정규화 및 저장
        for category, vector in updated_vectors.items():
            if np.any(vector):
                normalized = normalize([vector], norm='l2')[0]
                setattr(profile, category, normalized.tolist())
                
        profile.save()