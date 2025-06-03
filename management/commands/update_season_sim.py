from django.core.management.base import BaseCommand
from apps.items.models import ContentSummarize

class Command(BaseCommand):
    help = 'Update seasonal similarity for all contents'

    def handle(self, *args, **options):
        for obj in ContentSummarize.objects.all():
            obj.update_season_similarity()
        self.stdout.write(self.style.SUCCESS('Successfully updated all seasonal similarities'))