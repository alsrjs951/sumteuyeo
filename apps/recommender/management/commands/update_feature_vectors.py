# apps/items/management/commands/generate_feature_vectors.py
from django.core.management.base import BaseCommand
from django.db import transaction
from apps.items.models import ContentDetailCommon
from apps.recommender.models import ContentFeature
from tqdm import tqdm
import logging
import numpy as np

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Generate feature vectors for all ContentDetailCommon entries'

    def add_arguments(self, parser):
        parser.add_argument(
            '--chunk-size',
            type=int,
            default=1000,
            help='Number of records to process at a time'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update existing feature vectors'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show progress bar'
        )

    def handle(self, *args, **options):
        chunk_size = options['chunk_size']
        force_update = options['force']
        verbose = options['verbose']

        # 전체 콘텐츠 수 계산
        total_count = ContentDetailCommon.objects.count()
        success_count = 0
        error_count = 0

        # 진행률 표시 설정
        qs = ContentDetailCommon.objects.all().iterator(chunk_size=chunk_size)
        if verbose:
            qs = tqdm(qs, total=total_count, desc="Processing contents")

        for content in qs:
            try:
                with transaction.atomic():
                    # ContentFeature 객체 생성/조회
                    feature, created = ContentFeature.objects.get_or_create(
                        detail=content
                    )

                    # 기존 벡터가 있고 강제 업데이트가 아닌 경우 스킵
                    def is_valid_vector(vec):
                        # None, 빈 리스트, [None], [null] 등 모두 False로 간주
                        if vec is None:
                            return False
                        if not isinstance(vec, (list, np.ndarray)):
                            return False
                        if len(vec) == 0:
                            return False
                        # 모든 값이 None이거나 null인 경우
                        if all(v is None for v in vec):
                            return False
                        return True

                    # 사용 예시
                    if not created and not force_update and is_valid_vector(feature.feature_vector):
                        continue


                    # 특징 벡터 업데이트
                    if feature.update_feature_vector():
                        success_count += 1
                    else:
                        error_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to process contentid={content.contentid}: {str(e)}",
                    exc_info=True
                )
                error_count += 1

        # 결과 출력
        self.stdout.write("\nProcessing complete:")
        self.stdout.write(f" - Total items:   {total_count}")
        self.stdout.write(f" - Success:       {success_count}")
        self.stdout.write(f" - Errors:        {error_count}")
        if error_count > 0:
            self.stdout.write(self.style.ERROR("Some errors occurred. Check logs."))
