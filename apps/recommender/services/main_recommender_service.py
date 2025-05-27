from django.http import JsonResponse
from users.models import UserPreferenceProfile
from recommender.services.feature_service import FeatureService
import numpy as np
import logging

logger = logging.getLogger(__name__)

# 당신을 위한 추천 (1행)
def recommend_for_user_1(user_id: int) -> list:
    """사용자 프로필 기반 30개 콘텐츠 추천"""
    try:
        # 1. 사용자 프로필 벡터 조회
        profile = UserPreferenceProfile.objects.get(user_id=user_id)
        user_vector = np.array(profile.experience, dtype=np.float32)  # 관광지 카테고리 기준
        
        # 2. 유사 콘텐츠 검색 (최대 30개)
        similar_contents = FeatureService.find_similar_spots(user_vector, max_results=30)
        
        # 3. 추천 결과 가공
        recommendations = [
            {
                "contentid": content.detail.contentid,
                "title": content.detail.title,
                "image": content.detail.firstimage,
                "similarity_score": float(content.similarity)
            }
            for content in similar_contents
        ]
        
        # 4. 결과가 30개 미만일 경우 로깅
        if len(recommendations) < 30:
            logger.warning(f"Only {len(recommendations)} recommendations found for user {user_id}")
            
        return recommendations
    
    except UserPreferenceProfile.DoesNotExist:
        logger.error(f"No profile found for user {user_id}")
        return []
