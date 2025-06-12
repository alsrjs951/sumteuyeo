# users/management/commands/update_user_profiles.py

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.users.tasks import update_user_preference_task
import logging
import numpy as np

logger = logging.getLogger(__name__)
User = get_user_model()

class Command(BaseCommand):
    help = '사용자 프로필 벡터를 일괄 업데이트하는 명령어'

    def add_arguments(self, parser):
        parser.add_argument(
            '--user-id',
            type=int,
            help='특정 사용자 ID 지정'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='모든 사용자 프로필 업데이트'
        )
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Celery 작업 큐 대신 동기 방식 실행'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='일괄 처리 사용자 수 (기본값: 1000)'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(f"[{start_time}] 사용자 프로필 벡터 업데이트 시작...")

        try:
            if options['user_id']:
                self._process_single_user(options)
            elif options['all']:
                self._process_bulk_users(options)
            else:
                raise ValueError("--user-id 또는 --all 옵션 필수")

            elapsed = timezone.now() - start_time
            self.stdout.write(f"총 소요 시간: {elapsed.total_seconds():.2f}초")

        except Exception as e:
            logger.error(f"명령어 실행 실패: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"오류 발생: {str(e)}"))

    def _process_single_user(self, options):
        user = User.objects.get(pk=options['user_id'])
        
        if options['sync']:
            result = update_user_preference_task.apply(
                kwargs={'user_id': user.id}
            ).get()
            self.stdout.write(
                self.style.SUCCESS(f"사용자 {user.id} 동기 업데이트 완료: {result}")
            )
        else:
            async_result = update_user_preference_task.delay(user.id)
            self.stdout.write(
                self.style.SUCCESS(f"사용자 {user.id} 작업 큐 등록 (Task ID: {async_result.id})")
            )

    def _process_bulk_users(self, options):
        user_ids = User.objects.all().values_list('id', flat=True).iterator()
        total_count = 0
        batch = []
        
        for uid in user_ids:
            batch.append(uid)
            if len(batch) >= options['batch_size']:
                total_count += self._process_batch(batch, options)
                batch = []
        
        if batch:
            total_count += self._process_batch(batch, options)
        
        self.stdout.write(
            self.style.SUCCESS(f"총 {total_count}명 사용자 업데이트 작업 발송 완료")
        )

    def _process_batch(self, user_ids, options):
        if options['sync']:
            results = []
            for uid in user_ids:
                results.append(
                    update_user_preference_task.apply(kwargs={'user_id': uid}).get()
                )
            return len(results)
        else:
            async_results = [
                update_user_preference_task.delay(uid)
                for uid in user_ids
            ]
            return len(async_results)
