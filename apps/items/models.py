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

def get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                _model = SentenceTransformer('all-mpnet-base-v2')
    return _model

# 계절별 대표 문장 리스트 (멀티 센텐스 앙상블)
season_sentences = {
    'spring': ['벚꽃이 피는 계절', '따뜻한 봄바람', '피크닉하기 좋은 봄'],
    'summer': ['해변에서 수영', '여름 바캉스', '시원한 음료와 야외 활동'],
    'autumn': ['단풍이 아름다운 가을', '수확의 계절', '선선한 바람'],
    'winter': ['눈이 내리는 겨울', '스키와 온천', '따뜻한 음료']
}

# 계절별 임베딩 평균 계산 (초기화)
model = get_model()
season_embeddings = {
    season: np.mean([model.encode(s) for s in sentences], axis=0)
    for season, sentences in season_sentences.items()
}

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
        """요약 텍스트 기반 계절 유사도 갱신 (강력한 모델 + 멀티 센텐스 + 키워드 가중치)"""
        # 모델 로드
        model = get_model()
        # 텍스트 임베딩
        text_emb = model.encode(self.summarize_text)
        # 계절별 유사도 계산
        for season, emb in season_embeddings.items():
            cosine_sim = np.dot(text_emb, emb) / (norm(text_emb) * norm(emb))
            # 키워드 가중치 적용
            for kw in SEASON_KEYWORDS[season]:
                if kw in self.summarize_text:
                    cosine_sim = min(cosine_sim + 0.1, 1.0)
            setattr(self, f'{season}_sim', float(cosine_sim))
        self.save(update_fields=['spring_sim', 'summer_sim', 'autumn_sim', 'winter_sim'])


    class Meta:
        db_table = 'content_summarize'
