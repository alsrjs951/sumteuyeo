from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.contrib.auth import get_user_model
from pgvector.django import VectorField

User = get_user_model()

class UserPreferenceProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='preferences')
    # 3개 메인 카테고리별 484차원 벡터 (pgvector)
    experience = VectorField(dimensions=484, null=True, blank=True)        # 체험관광+역사+레저+자연+쇼핑+문화
    food = VectorField(dimensions=484, null=True, blank=True)              # 음식
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_preference_profile'
        indexes = [
            models.Index(fields=['user']),
        ]

class CategoryHierarchy(models.Model):
    code = models.CharField(max_length=10, unique=True)  # 예: AC01
    name = models.CharField(max_length=50)               # 예: 축제 > 공연
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True)
    embedding = ArrayField(models.FloatField(), size=100)  # 카테고리 임베딩

class GlobalPreferenceProfile(models.Model):
    """전체 사용자 선호도 집계 프로필"""
    experience = VectorField(dimensions=484)      # 체험관광+역사+레저+자연+쇼핑+문화
    food = VectorField(dimensions=484)            # 음식
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'global_preference_profile'
        verbose_name = '전역 선호도 프로필'

    def __str__(self):
        return f"Global Profile ({self.updated_at})"