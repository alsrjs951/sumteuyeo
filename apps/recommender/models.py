from django.db import models
from pgvector.django import VectorField, HnswIndex
from sentence_transformers import SentenceTransformer
from items.services.tourapi import get_summarize_tourist_spot
from functools import lru_cache
import numpy as np
import joblib
from items.models import ContentDetailCommon
from sklearn.preprocessing import normalize


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
        if cls._text_model is None:
            cls._text_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        return cls._text_model

    @classmethod
    def get_category_encoder(cls, level):
        if level not in cls._category_encoders:
            cls._category_encoders[level] = joblib.load(f'encoders/{level}_encoder.joblib')
        return cls._category_encoders[level]

    def get_text_embedding(self):
        summary_text = get_summarize_tourist_spot(self.detail.contentid, self.detail.contenttypeid)
        return self.get_text_model().encode(summary_text)

    def get_category_embedding(self):
        encodings = []
        for i, level in enumerate(['lcls1', 'lcls2', 'lcls3']):
            value = getattr(self.detail, f'lclsSystm{i+1}')
            encoder = self.get_category_encoder(level)
            weight = [0.4, 0.3, 0.3][i]
            enc = encoder.transform([[value]]).toarray()[0] * weight
            encodings.append(enc)
        return np.concatenate(encodings)

    def update_feature_vector(self):
        text_emb = self.get_text_embedding()
        cat_emb = self.get_category_embedding()
        
        # 벡터 결합 및 정규화
        combined = np.concatenate([text_emb, cat_emb])
        normalized = normalize(combined.reshape(1, -1), norm='l2', axis=1)  # L2 정규화
        
        self.feature_vector = normalized.flatten().tolist()  # 1차원 배열로 변환
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