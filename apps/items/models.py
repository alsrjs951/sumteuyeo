from django.db import models
from sentence_transformers import SentenceTransformer
from numpy.linalg import norm
import numpy as np
import threading

class ContentDetailCommon(models.Model):
    id = models.AutoField(primary_key=True)  # INTEGER, PK
    contentid = models.PositiveIntegerField(unique=True)
    contenttypeid = models.PositiveSmallIntegerField()
    title = models.TextField()
    createdtime = models.DateTimeField()
    modifiedtime = models.DateTimeField()
    tel = models.TextField(blank=True, null=True)
    telname = models.TextField(blank=True, null=True)
    homepage = models.TextField(blank=True, null=True)
    firstimage = models.TextField(blank=True, null=True)
    firstimage2 = models.TextField(blank=True, null=True)
    cpyrhtdivcd = models.TextField(blank=True, null=True)
    areacode = models.PositiveSmallIntegerField(blank=True, null=True)
    sigungucode = models.PositiveSmallIntegerField(blank=True, null=True)
    ldongregncd = models.TextField(blank=True, null=True)
    ldongsigngucd = models.TextField(blank=True, null=True)
    lclssystm1 = models.TextField(blank=True, null=True)
    lclssystm2 = models.TextField(blank=True, null=True)
    lclssystm3 = models.TextField(blank=True, null=True)
    cat1 = models.TextField(blank=True, null=True)
    cat2 = models.TextField(blank=True, null=True)
    cat3 = models.TextField(blank=True, null=True)
    addr1 = models.TextField(blank=True, null=True)
    addr2 = models.TextField(blank=True, null=True)
    zipcode = models.TextField(blank=True, null=True)
    mapx = models.FloatField(blank=True, null=True)  # DOUBLE PRECISION
    mapy = models.FloatField(blank=True, null=True)  # DOUBLE PRECISION
    mlevel = models.PositiveSmallIntegerField(blank=True, null=True)
    overview = models.TextField(blank=True, null=True)
    
    summarize = models.OneToOneField(
        'ContentSummarize',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='summarize'
    )

    class Meta:
        db_table = 'content_detail_common'
        indexes = [
            models.Index(fields=['contentid']),
            models.Index(fields=['mapx', 'mapy']),
        ]


class ContentDetailIntro(models.Model):
    contentid = models.PositiveIntegerField(unique=True)  # INTEGER, PK
    contenttypeid = models.PositiveSmallIntegerField()
    etc = models.JSONField()  # JSONB

    class Meta:
        db_table = 'content_detail_intro'
        indexes = [
            models.Index(fields=['contentid']),
        ]


class ContentDetailInfo(models.Model):
    contentid = models.PositiveIntegerField()  # INTEGER
    contenttypeid = models.PositiveSmallIntegerField()
    etc = models.JSONField()  # JSONB

    class Meta:
        db_table = 'content_detail_info'
        indexes = [
            models.Index(fields=['contentid']),
        ]


class ContentDetailImage(models.Model):
    contentid = models.PositiveIntegerField()  # INTEGER
    imgname = models.TextField()
    originimgurl = models.TextField()
    serialnum = models.TextField(unique=True)
    smallimageurl = models.TextField()
    cpyrhtdivcd = models.TextField()

    class Meta:
        db_table = 'content_detail_image'
        indexes = [
            models.Index(fields=['contentid']),
        ]

_lock = threading.Lock()
_model = None
_season_embeddings = {}
_season_norms = {}

def get_model() -> SentenceTransformer:
    """모델 및 계절 임베딩 싱글톤 초기화 (검색 결과 [4] 반영)"""
    global _model, _season_embeddings, _season_norms
    
    if _model is None:
        with _lock:
            if _model is None:
                # 1. 모델 초기화
                _model = SentenceTransformer('all-mpnet-base-v2')
                
                # 2. 계절 임베딩 사전 계산
                season_sentences = {
                    'spring': ['벚꽃이 피는 계절', '따뜻한 봄바람', '피크닉하기 좋은 봄'],
                    'summer': ['해변에서 수영', '여름 바캉스', '시원한 음료와 야외 활동'],
                    'autumn': ['단풍이 아름다운 가을', '수확의 계절', '선선한 바람'],
                    'winter': ['눈이 내리는 겨울', '스키와 온천', '따뜻한 음료']
                }
                
                # 3. 벡터화 최적화 (배치 처리)
                for season, sentences in season_sentences.items():
                    embeddings = _model.encode(sentences)
                    _season_embeddings[season] = np.mean(embeddings, axis=0)
                    _season_norms[season] = norm(_season_embeddings[season])
    
    return _model

# 키워드 가중치 사전
SEASON_KEYWORDS = {
    'spring': ['벚꽃', '꽃놀이', '봄꽃', '산책'],
    'summer': ['해변', '수영', '여름', '바캉스'],
    'autumn': ['단풍', '가을', '수확', '축제'],
    'winter': ['눈', '스키', '온천', '겨울']
}

class ContentSummarize(models.Model):
    contentid = models.PositiveIntegerField(unique=True)
    summarize_text = models.TextField()
    spring_sim = models.FloatField(default=0)
    summer_sim = models.FloatField(default=0)
    autumn_sim = models.FloatField(default=0)
    winter_sim = models.FloatField(default=0)

    def update_season_similarity(self):
        """최적화된 계절 유사도 계산 (메모리 항목 [1] 반영)"""
        # 1. 텍스트 임베딩
        model = get_model()
        text_emb = model.encode(self.summarize_text)
        text_norm = norm(text_emb)
        
        # 2. 제로 벡터 검사 (검색 결과 [5] 반영)
        if text_norm < 1e-8:
            return
            
        # 3. 계절별 유사도 계산
        for season in _season_embeddings.keys():
            emb = _season_embeddings[season]
            season_norm = _season_norms[season]
            
            # 4. 코사인 유사도 (벡터화 연산)
            cosine_sim = np.dot(text_emb, emb) / (text_norm * season_norm)
            
            # 5. 키워드 가중치 (최적화된 검색)
            keyword_count = sum(
                1 for kw in SEASON_KEYWORDS[season] 
                if kw in self.summarize_text
            )
            cosine_sim = min(cosine_sim + 0.1 * keyword_count, 1.0)
            
            setattr(self, f'{season}_sim', float(cosine_sim))

    @classmethod
    def bulk_update_season_similarities(cls, batch_size: int = 500):
        """벡터화 연산 최적화 버전 (검색 결과 [1][5] 반영)"""
        model = get_model()
        total = cls.objects.count()
        processed = 0
        
        while processed < total:
            batch = list(cls.objects.all()[processed:processed+batch_size])
            texts = [obj.summarize_text for obj in batch]
            
            # 1. 텍스트 임베딩 (배치 처리)
            text_embs = model.encode(
                texts, 
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            # 2. 노름 계산 (1D 배열로 변환)
            text_norms = np.linalg.norm(text_embs, axis=1)  # keepdims=False
            text_norms = np.where(text_norms < 1e-8, 1e-8, text_norms)
            
            # 3. 계절별 유사도 계산
            for season in _season_embeddings.keys():
                season_emb = _season_embeddings[season]
                season_norm = _season_norms[season]
                
                # 코사인 유사도 (벡터화 연산)
                cosine_sims = np.dot(text_embs, season_emb) / (text_norms * season_norm)
                
                # 키워드 가중치 적용 (NumPy 연산으로 변경)
                keyword_counts = np.array([
                    sum(1 for kw in SEASON_KEYWORDS[season] if kw in obj.summarize_text)
                    for obj in batch
                ])
                final_sims = np.minimum(cosine_sims + 0.1 * keyword_counts, 1.0)
                
                # 객체 속성 업데이트
                for idx, obj in enumerate(batch):
                    setattr(obj, f'{season}_sim', float(final_sims[idx]))
            
            # 4. 벌크 업데이트
            cls.objects.bulk_update(
                batch,
                ['spring_sim', 'summer_sim', 'autumn_sim', 'winter_sim'],
                batch_size=batch_size
            )
            
            processed += len(batch)
            print(f"진행: {processed}/{total} ({processed/total*100:.1f}%)")


    class Meta:
        db_table = 'content_summarize'
