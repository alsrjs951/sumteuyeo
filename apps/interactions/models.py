from django.db import models
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField

User = get_user_model()

class Questionnaire(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    weight = models.FloatField(default=1.0)  # 설문 가중치
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class QuestionCard(models.Model):
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE, related_name='cards')
    image = models.ImageField(upload_to='question_cards/')
    description = models.TextField()
    order = models.PositiveIntegerField(default=0)  # 카드 순서 지정

    def __str__(self):
        return f"{self.questionnaire.title} - Card {self.order+1}"

class QuestionnaireResponse(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    questionnaire = models.ForeignKey(Questionnaire, on_delete=models.CASCADE)
    selected_cards = models.ManyToManyField(QuestionCard)
    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'questionnaire')


class ContentInteraction(models.Model):
    ACTION_CHOICES = [
        ('click', '클릭'),
        ('bookmark', '찜'),
        ('like', '좋아요'),
        ('dislike', '싫어요'),
        ('share', '공유'),
        ('duration', '체류시간')
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.ForeignKey(
        'items.ContentDetailCommon',
        on_delete=models.CASCADE,
        db_column='content_id',
        to_field='contentid'  # 핵심 수정 부분
    )

    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    
    # 찜 상태 추적
    active = models.BooleanField(default=True, null=True, blank=True)
    
    # 체류 시간(초 단위)
    duration = models.FloatField(null=True, blank=True)
    
    # 자동 타임스탬프
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'content_interaction'
        indexes = [
            models.Index(fields=['user', 'content_id', 'action_type']),
            models.Index(fields=['action_type', 'timestamp']),
            models.Index(fields=['content_id']),
        ]

    def __str__(self):
        return f"{self.user} - {self.content_id} ({self.action_type})"
