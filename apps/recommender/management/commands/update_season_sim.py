from django.core.management.base import BaseCommand
from django.db.models import Q
from apps.items.models import ContentSummarize


class Command(BaseCommand):
    help = '대량 계절 유사도 갱신 (최적화 버전)'
    
    def add_arguments(self, parser):
        parser.add_argument('--batch-size', type=int, default=500,
                          help='배치 처리 단위 (기본값: 500)')
        parser.add_argument('--force', action='store_true',
                          help='기존 계산 결과 재계산')

    def handle(self, *args, **options):
        batch_size = options['batch_size']
        
        # 처리 대상 필터링
        queryset = ContentSummarize.objects.all()
        if not options['force']:
            queryset = queryset.filter(
                Q(spring_sim=0) | 
                Q(summer_sim=0) | 
                Q(autumn_sim=0) | 
                Q(winter_sim=0)
            )
        
        # 벌크 처리 실행
        ContentSummarize.bulk_update_season_similarities(batch_size)
        
        self.stdout.write(self.style.SUCCESS('성공적으로 갱신 완료'))
