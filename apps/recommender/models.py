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
import os
import logging
from sumteuyeo.settings import BASE_DIR
from pathlib import Path
from tqdm import tqdm
from django.db.models import F


_lock = threading.Lock()
logger = logging.getLogger(__name__)


class ContentFeature(models.Model):
    detail = models.OneToOneField(
        ContentDetailCommon,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column='detail_id',
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
            # 절대 경로 사용 (프로젝트 루트/encoders)
            encoder_dir = Path(BASE_DIR) / 'encoders'
            encoder_dir.mkdir(parents=True, exist_ok=True)
            encoder_path = encoder_dir / f'{level}_encoder.joblib'
            
            if not encoder_path.exists():
                raise FileNotFoundError(f"Encoder file not found: {encoder_path}")
                
            encoder_data = joblib.load(encoder_path)
            cls._category_encoders[level] = encoder_data
        return cls._category_encoders[level]


    def get_text_embedding(self):
        summary_text = get_summarize_content(self.detail.contentid, self.detail.contenttypeid)
        return self.get_text_model().encode(summary_text)

    def get_category_embedding(self):
        total_embedding = np.zeros(100, dtype=np.float32)
        dim_sizes = {'lcls1': 40, 'lcls2': 30, 'lcls3': 30}  # 레벨별 차원 크기

        for i, level in enumerate(['lcls1', 'lcls2', 'lcls3']):
            value = getattr(self.detail, f'lclssystm{i+1}', None)
            if not value:
                continue

            encoder_data = self.get_category_encoder(level)
            mapping = encoder_data['mapping']
            unknown_index = encoder_data['unknown_index']
            embedding_matrix = encoder_data['embedding_matrix']

            # 인덱스 찾기
            idx = mapping.get(value, unknown_index)

            # 임베딩 벡터 추출 및 차원 슬라이싱
            emb_vector_full = embedding_matrix[idx]
            target_dim = dim_sizes[level]
            emb_vector = emb_vector_full[:target_dim]

            # 시작 위치 계산 (대:0~39, 중:40~69, 소:70~99)
            start_idx = sum(list(dim_sizes.values())[:i])
            total_embedding[start_idx:start_idx+target_dim] = emb_vector

        return total_embedding



    def update_feature_vector(self):
        try:
            # 필수 정보 검증
            if not self.detail.contentid or not self.detail.contenttypeid:
                raise ValueError("Missing content ID or type ID")

            summary_text = get_summarize_content(self.detail.contentid, self.detail.contenttypeid)
            if not summary_text or not summary_text.strip():
                raise ValueError("Empty summary text")

            text_emb = self.get_text_embedding()
            if text_emb is None or len(text_emb) != 384:
                raise ValueError("Invalid text embedding")

            cat_emb = self.get_category_embedding()
            if cat_emb is None or len(cat_emb) != 100:
                raise ValueError("Invalid category embedding")

            combined = np.concatenate([text_emb, cat_emb])
            if len(combined) != 484:
                raise ValueError(f"Invalid combined vector dimension: {len(combined)}")

            combined_normalized = normalize(combined.reshape(1, -1), norm='l2', axis=1).flatten()
            self.feature_vector = combined_normalized.tolist()
            self.save(update_fields=['feature_vector'])
            return True

        except Exception as e:
            content_id = getattr(self.detail, "contentid", "UNKNOWN")
            logger.error(
                f"[ContentFeature] Feature vector update failed for contentid={content_id}: {str(e)}",
                exc_info=True
            )
            if self.feature_vector is not None:
                self.feature_vector = None
                self.save(update_fields=['feature_vector'])
            return False


    class Meta:
        db_table = 'content_feature'
        indexes = []