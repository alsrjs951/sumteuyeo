import numpy as np
from django.db.models import F, FloatField, Count, Q
from django.utils import timezone
from datetime import timedelta
from pgvector.django import CosineDistance
from apps.users.models import UserPreferenceProfile, GlobalPreferenceProfile
from apps.users.services.preference_service import PreferenceService
from ..models import ContentFeature
from apps.items.models import ContentDetailCommon
from apps.items.models import ContentSummarize
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import Cast
from django.db.models.expressions import RawSQL
from apps.interactions.models import ContentInteraction
from apps.items.services.tourapi import get_nearby_content_ids
import joblib
import logging
import random
import time
from typing import List, Dict
import json
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Q

logger = logging.getLogger(__name__)

VECTOR_DIM = 484  # 모델 차원 수
TOURIST_CATEGORIES = ["EX", "HS", "LS", "NA", "SH", "VE"]  # 관광지 카테고리
FOOD_CATEGORY = "FD"  # 음식점 카테고리

class ThemeRecommender:

    # 벡터 정규화 함수
    @staticmethod
    def l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else vec

    @staticmethod
    def generate_recommendation_rows(user_id: int, month: int, user_lat: float, user_lng: float) -> dict:
        """다양한 테마의 추천 행을 생성 (제목 포함)"""
        # 계절 이름 매핑 (영문)
        season_map = {
            12: 'winter', 1: 'winter', 2: 'winter',
            3: 'spring', 4: 'spring', 5: 'spring',
            6: 'summer', 7: 'summer', 8: 'summer',
            9: 'autumn', 10: 'autumn', 11: 'autumn'
        }
        
        rows = {
            'personalized': {'title': '당신을 위한 맞춤 추천', 'items': []},
            'hidden_gems': {'title': '나만 알고 싶은 숨은 명소', 'items': []},
            'hot_places': {'title': '실시간 인기 명소', 'items': []},
            'seasonal': {'title': f'{season_map.get(month, "특별")}에 가기 좋은 곳', 'items': []},
            'restaurants': {'title': '당신의 입맛을 저격할 맛집', 'items': []}
        }

        nearby_ids = get_nearby_content_ids(user_lat, user_lng)

        def get_db_results(blend_vec: np.ndarray, filters: Dict, size: int=30) -> List[int]:
            blend_vec_list = blend_vec.tolist()  # NumPy 배열을 리스트로 변환

            return (
                ContentDetailCommon.objects
                .select_related('feature')  # ContentFeature와 JOIN
                .annotate(
                    similarity=1 - CosineDistance(
                        'feature__feature_vector',  # 역방향 관계 접근
                        blend_vec_list
                    )
                )
                .filter(
                    **filters  # ContentDetailCommon 필드 직접 사용
                )
                .order_by('-similarity')  # 내림차순 정렬
                [: size]  # 상위 size개만 추출
            )

        # 1. 맞춤형 추천
        try:
            user_profile = UserPreferenceProfile.objects.get(user_id=user_id)
            user_exp = np.array(user_profile.experience, dtype=np.float32)
        except ObjectDoesNotExist:
            user_exp = np.zeros(VECTOR_DIM)

        # 가중치 동적 계산
        interaction_count = ContentInteraction.objects.filter(user_id=user_id).count()
        user_weight = PreferenceService.calculate_user_weight(interaction_count)
        global_weight = 1.0 - user_weight

        global_exp = GlobalPreferenceProfile.objects.first().experience
        try:
            global_exp_vec = np.array(global_exp, dtype=np.float32)
            assert global_exp_vec.size == VECTOR_DIM  # 차원 일치 확인
        except (TypeError, ValueError, AssertionError):
            global_exp_vec = np.zeros(VECTOR_DIM)

        
        blended_vec = ThemeRecommender.l2_normalize(user_weight*ThemeRecommender.l2_normalize(user_exp) + global_weight*ThemeRecommender.l2_normalize(global_exp_vec))
        
        rows['personalized']['items'] = get_db_results(
            blended_vec,
            {'lclssystm1__in': TOURIST_CATEGORIES, 'contentid__in': nearby_ids}
        )

        # 2. 숨은 명소
        try:
            # 저조한 상호작용 콘텐츠 ID 추출
            low_interaction_ids = (
                ContentDetailCommon.objects  # 모든 콘텐츠 대상
                .annotate(
                    interaction_count=Count(
                        'contentinteraction',  # ContentInteraction 모델의 related_name
                        filter=Q(contentinteraction__user__isnull=False)
                    )
                )
                .filter(contentid__in=nearby_ids)
                .filter(lclssystm1__in=TOURIST_CATEGORIES)
                .filter(
                    Q(interaction_count__isnull=True) | Q(interaction_count=0)
                )
                .order_by('interaction_count')
                .values_list('contentid', flat=True)[:30]
            )

            # 가중치 동적 계산
            hidden_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )
            
            rows['hidden_gems']['items'] = get_db_results(
                hidden_blend,
                {'contentid__in': low_interaction_ids},
                size=30
            )
        except Exception as e:
            logger.error(f"숨은 명소 추천 오류: {str(e)}")
            rows['hidden_gems']['items'] = []

        # 3. 핫한 명소
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        try:
            # 최근 7일 간 상호작용이 많은 콘텐츠 ID 추출
            hot_interaction_ids = (
                ContentDetailCommon.objects
                .annotate(
                    recent_interaction_count=Count(
                        'contentinteraction',
                        filter=Q(
                            contentinteraction__user__isnull=False,
                            contentinteraction__timestamp__gte=week_ago
                        )
                    )
                )
                .filter(contentid__in=nearby_ids)
                .filter(lclssystm1__in=TOURIST_CATEGORIES)
                .order_by('-recent_interaction_count')
                .values_list('contentid', flat=True)[:30]
            )

            # 핫한 명소 벡터 계산 (숨은 명소와 동일하게 가중치 적용)
            hot_blend = ThemeRecommender.l2_normalize(
                user_weight * ThemeRecommender.l2_normalize(user_exp) +
                global_weight * ThemeRecommender.l2_normalize(global_exp_vec)
            )

            # 검색 및 필터 적용
            rows['hot_places']['items'] = get_db_results(
                hot_blend,
                {'contentid__in': hot_interaction_ids},
                size=30
            )
        except Exception as e:
            logger.error(f"핫한 명소 추천 오류: {str(e)}")
            rows['hot_places']['items'] = []

        # 4. 계절 추천 (유사도 점수 기반)
        try:
            current_season = season_map.get(month, 'winter')

            # 가중치 동적 계산
            seasonal_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )

            # 계절 유사도가 높은 콘텐츠 ID 추출
            seasonal_ids = (
                ContentDetailCommon.objects
                .filter(contentid__in=nearby_ids)
                .filter(lclssystm1__in=TOURIST_CATEGORIES)
                .filter(summarize__isnull=False)  # 요약 정보가 있는 경우만
                .order_by(f'-summarize__{current_season}_sim')  # OneToOne 관계 접근
                .values_list('contentid', flat=True)[:30]
            )

            if current_season == 'winter':
                rows['seasonal']['title'] = '겨울에 가기 좋은 곳'
            elif current_season == 'spring':
                rows['seasonal']['title'] = '봄에 가기 좋은 곳'
            elif current_season == 'summer':
                rows['seasonal']['title'] = '여름에 가기 좋은 곳'
            elif current_season == 'autumn':
                rows['seasonal']['title'] = '가을에 가기 좋은 곳'
            else:
                rows['seasonal']['title'] = '여름에 가기 좋은 곳'

            rows['seasonal']['items'] = get_db_results(
                seasonal_blend,
                {'contentid__in': seasonal_ids},
                size=30
            )

        except Exception as e:
            logger.error(f"계절 추천 오류: {str(e)}", exc_info=True)
            rows['seasonal']['items'] = []

        # 5. 맛집 추천
        try:
            user_food = np.array(user_profile.food, dtype=np.float32)
        except:
            user_food = np.zeros(VECTOR_DIM)

        global_food = GlobalPreferenceProfile.objects.first().food
        global_food_vec = np.array(global_food, dtype=np.float32) if global_food is not None else np.zeros(VECTOR_DIM)
        
        # 가중치 동적 계산
        food_blend = ThemeRecommender.l2_normalize(user_weight*ThemeRecommender.l2_normalize(user_food) + global_weight*ThemeRecommender.l2_normalize(global_food_vec))
        
        rows['restaurants']['items'] = get_db_results(
            food_blend,
            {'lclssystm1': FOOD_CATEGORY, 'contentid__in': nearby_ids}
        )

        return rows
