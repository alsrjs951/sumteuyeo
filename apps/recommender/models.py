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
import faiss
import os
from sumteuyeo.settings import FAISS_BASE_DIR
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

    

    @classmethod
    def build_faiss_index(cls, index_path=FAISS_BASE_DIR / 'content_index.faiss', batch_size=1000):
        """FAISS 인덱스 생성 (배치 처리 및 메모리 최적화)"""
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        
        # 유효한 feature_vector가 있는 객체 쿼리
        qs = cls.objects.exclude(feature_vector__isnull=True)\
                       .select_related('detail')\
                       .annotate(contentid=F('detail__contentid'))\
                       .order_by('contentid')

        if not qs.exists():
            raise ValueError("생성할 특징 벡터가 존재하지 않습니다")

        # 첫 번째 벡터로 차원 확인
        first_vec = qs.first().feature_vector
        if isinstance(first_vec, list):
            first_vec = np.array(first_vec, dtype=np.float32)
        dim = len(first_vec)

        # FAISS 인덱스 초기화 (코사인 유사도용)
        index = faiss.IndexFlatIP(dim)
        
        # 벡터 및 ID 저장 리스트
        all_vectors = []
        all_ids = []
        
        # 배치 처리 진행률 표시
        total = qs.count()
        with tqdm(total=total, desc="FAISS 인덱스 빌드 중") as pbar:
            for offset in range(0, total, batch_size):
                batch = list(qs[offset:offset+batch_size])
                
                # 벡터 변환 및 유효성 검사
                vectors = []
                ids = []
                for obj in batch:
                    vec = obj.feature_vector
                    # 1차 검증: None 또는 빈 리스트
                    if vec is None or vec.size == 0 or np.all(vec == None) or np.isnan(vec).any():
                        continue
                    
                    # 2차 검증: 숫자형 데이터 확인
                    try:
                        vec = np.array(vec, dtype=np.float32)
                    except ValueError:
                        continue
                    
                    # 3차 검증: 차원 및 NaN 확인
                    if vec.ndim != 1 or vec.shape[0] != dim or np.isnan(vec).any():
                        continue
                    
                    vectors.append(vec)
                    ids.append(obj.contentid)
                
                if vectors:
                    # 배치 벡터 정규화 후 추가
                    vectors = np.vstack(vectors)
                    vectors = vectors.astype(np.float32)
                    faiss.normalize_L2(vectors)  # 코사인 유사도 정규화
                    index.add(vectors)
                    
                    all_vectors.append(vectors)
                    all_ids.extend(ids)
                    pbar.update(len(vectors))

        # ID 매핑 파일 저장
        id_map_path = index_path.with_name(f"{index_path.stem}_ids.npy")
        np.save(id_map_path, np.array(all_ids))

        # 인덱스 저장
        faiss.write_index(index, str(index_path))
        
        return str(index_path), str(id_map_path)


    class Meta:
        db_table = 'content_feature'
        indexes = []