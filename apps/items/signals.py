from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ContentSummarize

@receiver(post_save, sender=ContentSummarize, dispatch_uid="update_season_sim")
def update_similarity(sender, instance, **kwargs):
    if not hasattr(instance, '_updating_season_sim'):
        instance._updating_season_sim = True
        instance.update_season_similarity()
        del instance._updating_season_sim