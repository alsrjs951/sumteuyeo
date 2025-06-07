from django.db import models
from pgvector.django import VectorField, HnswIndex
from sentence_transformers import SentenceTransformer
from apps.items.services.tourapi import get_summarize_content
from functools import lru_cache
import numpy as np
import joblib
from apps.items.models import ContentDetailCommon
from sklearn.preprocessing import normalize
import threading
_lock = threading.Lock()


class ContentFeature(models.Model):
    detail = models.OneToOneField(
        ContentDetailCommon,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='contentid',
        related_name='feature'
    )
    feature_vector = VectorField(dimensions=484, null=True, blank=True)

    _text_model = None
    _category_encoders = {}

    @classmethod
    def get_text_model(cls):
        with _lock:
            if cls._text_model is None:
                cls._text_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        return cls._text_model

    @classmethod
    def get_category_encoder(cls, level):
        if level not in cls._category_encoders:
            cls._category_encoders[level] = joblib.load(f'encoders/{level}_encoder.joblib')
        return cls._category_encoders[level]

    def get_text_embedding(self):
        summary_text = get_summarize_content(self.detail.contentid, self.detail.contenttypeid)
        return self.get_text_model().encode(summary_text)

    def get_category_embedding(self):
        weighted_sum = np.zeros(100, dtype=np.float32)
        
        for i, level in enumerate(['lcls1', 'lcls2', 'lcls3']):
            value = getattr(self.detail, f'lclsSystm{i+1}')
            encoder_data = self.get_category_encoder(level)
            
            # 카테고리 → 인덱스 매핑
            idx = encoder_data['mapping'].get(value, encoder_data['unknown_index'])
            
            # 임베딩 벡터 조회
            emb = encoder_data['embedding_matrix'][idx]
            weight = [0.4, 0.3, 0.3][i]
            
            weighted_sum += emb * weight
            
        return weighted_sum



    def update_feature_vector(self):
        text_emb = self.get_text_embedding()
        cat_emb = self.get_category_embedding()
        
        # 벡터 결합
        combined = np.concatenate([text_emb, cat_emb])
        
        # 정규화 여부 확인 (수정 필요)
        model = self.get_text_model()
        if not getattr(model, '_normalize_embeddings', False):  # 더 안전한 확인 방법
            combined = normalize(combined.reshape(1, -1), norm='l2', axis=1).flatten()
        else:
            combined = combined.reshape(1, -1).flatten()
        
        # 차원 검증 (중요!)
        if len(combined) != 484:
            raise ValueError(f"Invalid dimension: {len(combined)} (expected 484)")
        
        self.feature_vector = combined.tolist()
        self.save(update_fields=['feature_vector'])


    class Meta:
        db_table = 'content_feature'
        indexes = [
            HnswIndex(
                fields=['feature_vector'],
                name='feature_vector_cosine_idx',
                opclasses=['vector_cosine_ops'],
                m=16,
                ef_construction=64
            )
        ]