from django.db import models
from sentence_transformers import SentenceTransformer
from numpy.linalg import norm
import numpy as np

class ContentDetailCommon(models.Model):
    contentid = models.PositiveIntegerField(unique=True)  # INTEGER, PK
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

model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')

season_sentences = {
    'spring': '벚꽃이 피고 따뜻한 날씨가 시작되는 봄은 꽃구경과 피크닉에 적합한 계절입니다.',
    'summer': '뜨거운 태양과 해변, 수영, 시원한 음료가 어울리는 여름은 휴가와 야외 활동의 계절입니다.',
    'autumn': '단풍이 물들고 선선한 바람이 부는 가을은 산책과 수확 축제가 활발한 시기입니다.',
    'winter': '눈이 내리고 추운 날씨가 지속되는 겨울은 스키, 온천, 따뜻한 음료가 인기인 계절입니다.'
}

# 계절 임베딩 생성
season_embeddings = {
    season: model.encode(sentence) 
    for season, sentence in season_sentences.items()
}


class ContentSummarize(models.Model):
    contentid = models.PositiveIntegerField(unique=True)
    summarize_text = models.TextField()
    spring_sim = models.FloatField(default=0)  # 봄 유사도
    summer_sim = models.FloatField(default=0)  # 여름 유사도
    autumn_sim = models.FloatField(default=0)  # 가을 유사도
    winter_sim = models.FloatField(default=0)  # 겨울 유사도

    def update_season_similarity(self):
        """요약 텍스트 기반 계절 유사도 갱신"""
        text_emb = model.encode(self.summarize_text)
        
        for season, emb in season_embeddings.items():
            # 코사인 유사도 계산
            cosine_sim = np.dot(text_emb, emb) / (norm(text_emb)*norm(emb))
            setattr(self, f'{season}_sim', float(cosine_sim))
        
        self.save()

    class Meta:
        db_table = 'content_summarize'
