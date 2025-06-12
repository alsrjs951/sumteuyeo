# users/management/commands/update_global_profile.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from apps.users.tasks import update_global_profile_task
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '글로벌 프로필을 즉시 업데이트하는 명령어 (벡터 분석 포함)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sync',
            action='store_true',
            help='Celery 작업 큐 대신 동기 방식으로 실행'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='최소 사용자 수 조건 무시하고 강제 실행'
        )

    def handle(self, *args, **options):
        start_time = timezone.now()
        self.stdout.write(f"[{start_time}] 글로벌 프로필 업데이트 시작...")

        try:
            if options['sync']:
                # 동기 실행 (개발용)
                result = update_global_profile_task.apply(
                    kwargs={'force': options['force']}
                ).get()
                self.stdout.write(self.style.SUCCESS(f"동기 실행 완료: {result}"))
            else:
                # 비동기 실행 (운영용)
                async_result = update_global_profile_task.delay(force=options['force'])
                self.stdout.write(
                    self.style.SUCCESS(f"작업이 Celery에 전달됨 (Task ID: {async_result.id})")
                )
            
            elapsed = timezone.now() - start_time
            self.stdout.write(f"총 소요 시간: {elapsed.total_seconds():.2f}초")

        except Exception as e:
            logger.error(f"명령어 실행 실패: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f"오류 발생: {str(e)}"))
