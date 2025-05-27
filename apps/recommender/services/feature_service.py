# services/feature_service.py
from django.core.exceptions import ObjectDoesNotExist
from pgvector.django import CosineDistance
import numpy as np
from typing import List, Dict
from recommender.models import ContentFeature

class FeatureService:
    VECTOR_DIM = 484  # 384(텍스트) + 100(카테고리)

    @staticmethod
    def get_feature_vector(contentid: int) -> np.ndarray:
        """정규화된 특성 벡터 반환"""
        try:
            content = ContentFeature.objects.get(pk=contentid)
            return np.array(content.feature_vector, dtype=np.float32)
        except ObjectDoesNotExist:
            raise ValueError(f"ContentID {contentid} not found")

    # 반드시 query_vector 는 L2 정규화를 한 후, 해당 함수를 호출해야함.
    @staticmethod
    def find_similar_spots(
        query_vector: np.ndarray, 
        global_vector: np.ndarray = None,  # 신규 추가: 전역 벡터
        blend_weight: float = 0.7,        # 개인 벡터 가중치 (0.5~0.8 권장)
        max_results: int = 10
    ):
        """개인/전역 벡터 혼합 유사도 검색"""
        
        # 벡터 검증
        if query_vector.shape != (FeatureService.VECTOR_DIM,):
            raise ValueError(f"개인 벡터 차원 불일치: {FeatureService.VECTOR_DIM} 필요")
        if global_vector is not None and global_vector.shape != (FeatureService.VECTOR_DIM,):
            raise ValueError(f"전역 벡터 차원 불일치: {FeatureService.VECTOR_DIM} 필요")

        # 벡터 혼합 (개인 70% + 전역 30%)
        if global_vector is not None:
            # 전역 벡터 정규화
            global_norm = global_vector / np.linalg.norm(global_vector)
            
            # 혼합 벡터 계산
            blended_vector = (blend_weight * query_vector) + ((1 - blend_weight) * global_norm)
            blended_vector /= np.linalg.norm(blended_vector)  # 재정규화
        else:
            blended_vector = query_vector  # 전역 벡터 없을 경우 원본 사용

        # 유사도 검색
        return (
            ContentFeature.objects
            .annotate(
                similarity=CosineDistance('feature_vector', blended_vector)  # 혼합 벡터 사용
            )
            .order_by('similarity')
            .select_related('detail')
            [:max_results]
        )


    @staticmethod
    def get_bulk_vectors(contentids: List[int]) -> Dict[int, np.ndarray]:
        """벌크 조회 최적화 버전"""
        return {
            obj.pk: np.array(obj.feature_vector, dtype=np.float32)
            for obj in ContentFeature.objects.filter(pk__in=contentids)
        }
