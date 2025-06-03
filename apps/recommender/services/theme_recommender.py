import numpy as np
from django.db.models import F, FloatField, Count, Q
from django.utils import timezone
from datetime import timedelta
from pgvector.django import CosineDistance
from apps.users.models import UserPreferenceProfile, GlobalPreferenceProfile
from ..models import ContentFeature
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

logger = logging.getLogger(__name__)

VECTOR_DIM = 484  # 모델 차원 수
TOURIST_CATEGORIES = ["EX", "HS", "LS", "NA", "SH", "VE"]  # 관광지 카테고리
FOOD_CATEGORY = "FD"  # 음식점 카테고리

class ThemeRecommender:

    # 벡터 정규화 함수
    @staticmethod
    def l2_normalize(vec):
        norm = np.linalg.norm(vec)
        return vec / norm if norm > 1e-8 else vec

    @staticmethod
    def generate_recommendation_rows(user_id: int, month: int, user_lat: float, user_lng: float) -> dict:
        """다양한 테마의 추천 행을 생성 (제목 포함)"""
        
        rows = {
            'personalized': {'title': '당신을 위한 맞춤 추천', 'items': []},
            'preferred_subcat_1': {'title': '', 'items': []},
            'preferred_subcat_2': {'title': '', 'items': []},
            'seasonal': {'title': f'{season_map.get(month, "특별")} 추천', 'items': []},
            'hidden_gems': {'title': '숨은 명소', 'items': []},
            'restaurants': {'title': '당신의 입맛을 저격할 맛집', 'items': []}
        }

        # 1. 맞춤형 추천
        try:
            user_profile = UserPreferenceProfile.objects.get(user_id=user_id)
            user_exp = np.array(user_profile.experience, dtype=np.float32)
        except ObjectDoesNotExist:
            user_exp = np.zeros(VECTOR_DIM)

        # 가중치 동적 계산
        interaction_count = ContentInteraction.objects.filter(user_id=user_id).count()
        user_weight = UserPreferenceProfile.calculate_user_weight(interaction_count)
        global_weight = 1.0 - user_weight

        global_exp = GlobalPreferenceProfile.objects.first().experience
        global_exp_vec = np.array(global_exp, dtype=np.float32) if global_exp else np.zeros(VECTOR_DIM)
        
        blended_vec = ThemeRecommender.l2_normalize(user_weight*ThemeRecommender.l2_normalize(user_exp) + global_weight*ThemeRecommender.l2_normalize(global_exp_vec))
        rows['personalized']['items'] = (
            ContentFeature.objects
            .filter(contentid__in=get_nearby_content_ids(user_lat, user_lng))
            .filter(detail__lclssystm1__in=TOURIST_CATEGORIES)
            .annotate(
                similarity=CosineDistance('feature_vector', blended_vec)
            )
            .order_by('similarity')[:30]
        )

        # 2. 선호 소분류 추천
        try:
            if np.linalg.norm(user_exp) > 1e-8:
                # 계층별 인코더 사이즈 확인
                lcls1_encoder = ContentFeature.get_category_encoder('lcls1')
                lcls2_encoder = ContentFeature.get_category_encoder('lcls2')
                lcls3_encoder = ContentFeature.get_category_encoder('lcls3')
                
                lcls1_dim = len(lcls1_encoder.categories_[0])
                lcls2_dim = len(lcls2_encoder.categories_[0])
                lcls3_dim = len(lcls3_encoder.categories_[0])
                
                # lcls3 벡터 영역 추출
                lcls3_start = lcls1_dim + lcls2_dim
                lcls3_vector = user_exp[384+lcls3_start : 384+lcls3_start+lcls3_dim]
                
                # 상위 2개 인덱스
                top_indices = np.argsort(lcls3_vector)[-2:][::-1]
                
                # 실제 카테고리명 변환
                subcategories = lcls3_encoder.inverse_transform(
                    np.array(top_indices).reshape(-1, 1)
                ).flatten()

                for i, subcat in enumerate(subcategories, 1):
                    row_key = f'preferred_subcat_{i}'
                    rows[row_key]['title'] = f'#{subcat} 핫플레이스'

                    # 가중치 동적 계산
                    subcat_blend = ThemeRecommender.l2_normalize(
                        user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                        global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
                    )

                    rows[row_key]['items'] = (
                        ContentFeature.objects
                        .filter(detail__lclssystm3=subcat,
                                contentid__in=get_nearby_content_ids(user_lat, user_lng),
                                detail__lclssystm1=TOURIST_CATEGORIES
                                )
                        .annotate(
                            similarity=CosineDistance('feature_vector', subcat_blend)
                        )
                        .order_by('similarity')[:30]
                    )

        except Exception as e:
            logger.error(f"소분류 추천 오류: {str(e)}")

        # 3. 계절 추천 (유사도 점수 기반)
        try:
            # 계절 이름 매핑 (영문)
            season_map = {
                12: 'winter', 1: 'winter', 2: 'winter',
                3: 'spring', 4: 'spring', 5: 'spring',
                6: 'summer', 7: 'summer', 8: 'summer',
                9: 'autumn', 10: 'autumn', 11: 'autumn'
            }
            current_season = season_map.get(month, 'winter')
            
            # 계절 유사도 상위 콘텐츠 선별 (0.7 이상)
            seasonal_contents = (
                ContentSummarize.objects
                .filter(**{f'{current_season}_sim__gte': 0.7})
                .values_list('contentid', flat=True)
            )

            # 가중치 동적 계산
            seasonal_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )
            
            # 개인화 + 계절 특징 결합 추천
            rows['seasonal']['items'] = (
                ContentFeature.objects
                .select_related('detail')
                .filter(Q(contentid__in=seasonal_contents) &
                        Q(contentid__in=get_nearby_content_ids(user_lat, user_lng)),
                        detail__lclssystm1__in=TOURIST_CATEGORIES
                        )
                .annotate(
                    similarity=CosineDistance('feature_vector', seasonal_blend)  # 개인화 벡터
                )
                .order_by('-similarity')[:30]  # 유사도 높은 순
            )

        except Exception as e:
            logger.error(f"계절 추천 오류: {str(e)}", exc_info=True)
            rows['seasonal']['items'] = []


        # 4. 숨은 명소
        try:
            # 저조한 상호작용 콘텐츠 ID 추출
            low_interaction_ids = (
                ContentInteraction.objects
                .values('content_id')
                .annotate(interaction_count=Count('id'))
                .filter(interaction_count__lt=20)  # 상호작용 20개 이내 콘텐츠 추출
                .values_list('content_id', flat=True)
            )

            # 가중치 동적 계산
            hidden_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )
            
            rows['hidden_gems']['items'] = (
                ContentFeature.objects
                .select_related('detail')
                .filter(
                    Q(contentid__in=low_interaction_ids) &
                    Q(detail__mapx__isnull=False) &
                    Q(detail__mapy__isnull=False) &
                    Q(contentid__in=get_nearby_content_ids(user_lat, user_lng)) &
                    Q(detail__lclssystm1__in=TOURIST_CATEGORIES)
                )
                .annotate(
                    similarity=CosineDistance('feature_vector', hidden_blend)
                )
                .order_by('similarity')[:30]  # 유사도 높은 순으로 정렬
            )
        except Exception as e:
            logger.error(f"숨은 명소 추천 오류: {str(e)}")
            rows['hidden_gems']['items'] = []

        # 5. 맛집 추천
        try:
            user_food = np.array(user_profile.food, dtype=np.float32)
        except:
            user_food = np.zeros(VECTOR_DIM)

        global_food = GlobalPreferenceProfile.objects.first().food
        global_food_vec = np.array(global_food, dtype=np.float32) if global_food else np.zeros(VECTOR_DIM)
        
        # 가중치 동적 계산
        food_blend = ThemeRecommender.l2_normalize(user_weight*ThemeRecommender.l2_normalize(user_food) + global_weight*ThemeRecommender.l2_normalize(global_food_vec))
        rows['restaurants']['items'] = ContentFeature.objects.annotate(
            similarity=CosineDistance('feature_vector', food_blend)
        ).filter(content__in=get_nearby_content_ids(user_lat, user_lng),
                 detail__lclssystm1=FOOD_CATEGORY
                 ).order_by('similarity')[:30]

        return rows
