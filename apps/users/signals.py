from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from apps.recommender.models import UserPreferenceProfile

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_preference_profile(sender, instance, created, **kwargs):
    if created:
        UserPreferenceProfile.objects.create(user=instance)
