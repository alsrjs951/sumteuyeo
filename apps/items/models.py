from django.db import models

# Create your models here.
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
    cpyrhtDivCd = models.TextField(blank=True, null=True)
    areacode = models.PositiveSmallIntegerField(blank=True, null=True)
    sigungucode = models.PositiveSmallIntegerField(blank=True, null=True)
    lDongRegnCd = models.TextField(blank=True, null=True)
    lDongSignguCd = models.TextField(blank=True, null=True)
    lclsSystm1 = models.TextField(blank=True, null=True)
    lclsSystm2 = models.TextField(blank=True, null=True)
    lclsSystm3 = models.TextField(blank=True, null=True)
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
    contentid = models.PositiveIntegerField(unique=True)  # INTEGER, PK
    contenttypeid = models.PositiveSmallIntegerField()
    etc = models.JSONField()  # JSONB

    class Meta:
        db_table = 'content_detail_info'
        indexes = [
            models.Index(fields=['contentid']),
        ]


class ContentDetailImage(models.Model):
    contentid = models.PositiveIntegerField(unique=True)  # INTEGER
    imgname = models.TextField()
    originimgurl = models.TextField()
    serialnum = models.TextField()
    smallimageurl = models.TextField()
    cpyrhtDivCd = models.TextField()

    class Meta:
        db_table = 'content_detail_image'
        indexes = [
            models.Index(fields=['contentid']),
        ]


class ContentSummarize(models.Model):
    contentid = models.PositiveIntegerField(unique=True)
    summarize_text = models.TextField()

    class Meta:
        db_table = 'content_summarize'
