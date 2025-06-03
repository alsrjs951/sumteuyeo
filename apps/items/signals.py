from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ContentSummarize

@receiver(post_save, sender=ContentSummarize)
def update_similarity(sender, instance, **kwargs):
    instance.update_season_similarity()
