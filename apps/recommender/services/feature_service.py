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
    def find_similar_spots(query_vector: np.ndarray, max_results: int = 10):
        """정규화된 쿼리 벡터 기반 유사도 검색"""
        # 입력 벡터 검증
        if query_vector.shape != (FeatureService.VECTOR_DIM,):
            raise ValueError(f"Vector must have {FeatureService.VECTOR_DIM} dimensions")
            
        return (
            ContentFeature.objects
            .annotate(similarity=CosineDistance('feature_vector', query_vector))
            .order_by('similarity')
            .select_related('detail')  # 성능 향상
            [:max_results]
        )

    @staticmethod
    def get_bulk_vectors(contentids: List[int]) -> Dict[int, np.ndarray]:
        """벌크 조회 최적화 버전"""
        return {
            obj.pk: np.array(obj.feature_vector, dtype=np.float32)
            for obj in ContentFeature.objects.filter(pk__in=contentids)
        }
