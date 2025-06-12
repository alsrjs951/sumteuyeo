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
import faiss
from .chatbot.faiss_manager import FaissManager
from sumteuyeo.settings import FAISS_BASE_DIR
from typing import List, Dict
import json

logger = logging.getLogger(__name__)

VECTOR_DIM = 484  # 모델 차원 수
TOURIST_CATEGORIES = ["EX", "HS", "LS", "NA", "SH", "VE"]  # 관광지 카테고리
FOOD_CATEGORY = "FD"  # 음식점 카테고리

class ThemeRecommender:
    # def __init__(self):
    #     self.faiss_manager = FaissManager(
    #         index_path=FAISS_BASE_DIR / "content_index.faiss",
    #         id_map_path=FAISS_BASE_DIR / "content_index_ids.npy"
    #     )

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
            'preferred_subcat_1': {'title': '', 'items': []},
            'preferred_subcat_2': {'title': '', 'items': []},
            'seasonal': {'title': f'{season_map.get(month, "특별")} 추천', 'items': []},
            'hidden_gems': {'title': '숨은 명소', 'items': []},
            'restaurants': {'title': '당신의 입맛을 저격할 맛집', 'items': []}
        }

        nearby_ids = get_nearby_content_ids(user_lat, user_lng)

        # FAISS 검색 공통 함수
        def get_faiss_results(blend_vec: np.ndarray, filters: Dict) -> List[int]:
            faiss_manager = FaissManager(
                index_path=FAISS_BASE_DIR / "content_index.faiss",
                id_map_path=FAISS_BASE_DIR / "content_index_ids.npy"
            )
            faiss_ids = faiss_manager.search(blend_vec, 30000)
            
            # 위치 필터링 적용
            filtered_ids = list(set(faiss_ids) & set(nearby_ids))
            
            # 추가 필터 적용 (카테고리 등)
            return ContentDetailCommon.objects.filter(
                contentid__in=filtered_ids
            ).filter(**filters)[:30]

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
        
        rows['personalized']['items'] = get_faiss_results(
            blended_vec,
            {'lclssystm1__in': TOURIST_CATEGORIES}
        )

        # 2. 선호 소분류 추천
        try:
            # ▼▼▼ 조건 제거 (항상 실행) ▼▼▼
            lcls2_encoder = ContentFeature.get_category_encoder('lcls2')
            assert lcls2_encoder is not None, "lcls2 인코더 없음"

            with open('apps/items/services/cat_dict.json', 'rb') as f:
                cat_dict = json.load(f)
            
            # 중분류 벡터 영역 추출 (고정 차원)
            lcls2_start = 0  # 대분류(40)
            lcls2_dim = 40  # 중분류 차원
            lcls2_vector = user_exp[384 + lcls2_start : 384 + lcls2_start + lcls2_dim]
            
            # ▼▼▼ 제로 벡터 대비 정규화 ▼▼▼
            lcls2_vector = ThemeRecommender.l2_normalize(lcls2_vector)
            if np.all(lcls2_vector == 0):  # 완전한 제로 벡터일 경우
                lcls2_vector = ThemeRecommender.l2_normalize(global_exp_vec[384 + lcls2_start : 384 + lcls2_start + lcls2_dim])
            
            # Softmax 적용
            probs = np.exp(lcls2_vector) / np.sum(np.exp(lcls2_vector))
            top_indices = np.argsort(probs)[-2:][::-1]
            
            # 실제 카테고리명 변환
            encoder = lcls2_encoder['encoder']

            valid_indices = [idx for idx in top_indices if idx < len(encoder.categories_[0])]
            subcategories = encoder.categories_[0][valid_indices]

            for i, subcat in enumerate(subcategories, 1):
                row_key = f'preferred_subcat_{i}'
                print(subcat + " 입니다.")
                kr_subcat = cat_dict.get(subcat, "알 수 없는")
                rows[row_key]['title'] = f'#{kr_subcat} 핫플레이스'
                
                # ▼▼▼ 가중치 재계산 (제로 벡터도 처리) ▼▼▼
                subcat_blend = ThemeRecommender.l2_normalize(
                    user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                    global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
                )
                
                rows[row_key]['items'] = get_faiss_results(
                    subcat_blend,
                    {'lclssystm2': subcat}
                )

        except Exception as e:
            logger.error(f"중분류 추천 오류: {str(e)}", exc_info=True)


        # 3. 계절 추천 (유사도 점수 기반)
        try:
            current_season = season_map.get(month, 'winter')

            # 가중치 동적 계산
            seasonal_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )

            # 계절 유사도가 높은 콘텐츠 ID 추출
            seasonal_ids = ContentSummarize.objects.filter(
                **{f'{current_season}_sim__gte': 0.7}
            ).values_list('contentid', flat=True)


            if current_season == 'winter':
                rows['seasonal']['title'] = '겨울 추천'
            elif current_season == 'spring':
                rows['seasonal']['title'] = '봄 추천'
            elif current_season == 'summer':
                rows['seasonal']['title'] = '여름 추천'
            elif current_season == 'autumn':
                rows['seasonal']['title'] = '가을 추천'
            
            rows['seasonal']['items'] = get_faiss_results(
                seasonal_blend,
                {'contentid__in': seasonal_ids, 'lclssystm1__in': TOURIST_CATEGORIES}
            )

        except Exception as e:
            logger.error(f"계절 추천 오류: {str(e)}", exc_info=True)
            rows['seasonal']['items'] = []


        # 4. 숨은 명소
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
                .filter(
                    Q(interaction_count__lt=20) | 
                    Q(interaction_count__isnull=True)  # 상호작용 0개 포함
                )
                .values_list('contentid', flat=True)[:10000]
            )


            # 가중치 동적 계산
            hidden_blend = ThemeRecommender.l2_normalize(
                user_weight*ThemeRecommender.l2_normalize(user_exp) + 
                global_weight*ThemeRecommender.l2_normalize(global_exp_vec)
            )
            
            rows['hidden_gems']['items'] = get_faiss_results(
                hidden_blend,
                {'contentid__in': low_interaction_ids}
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
        global_food_vec = np.array(global_food, dtype=np.float32) if global_food is not None else np.zeros(VECTOR_DIM)

        
        # 가중치 동적 계산
        food_blend = ThemeRecommender.l2_normalize(user_weight*ThemeRecommender.l2_normalize(user_food) + global_weight*ThemeRecommender.l2_normalize(global_food_vec))
        
        rows['restaurants']['items'] = get_faiss_results(
            food_blend,
            {'lclssystm1': FOOD_CATEGORY}
        )

        return rows
