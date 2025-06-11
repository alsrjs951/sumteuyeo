from django.core.management.base import BaseCommand
from django.db import transaction
from pathlib import Path
import numpy as np
import faiss
import os
from apps.items.models import ContentSummarize
from apps.recommender.models import ContentFeature
from sumteuyeo.settings import FAISS_BASE_DIR
import logging
from tqdm import tqdm  # 진행률 표시

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'FAISS 인덱스 빌드 (배치 처리 최적화)'

    # ex) python manage.py build_faiss_index --batch-size 1000
    def handle(self, *args, **options):
        try:
            # 모델 클래스 메서드 직접 호출
            index_path, id_path = ContentFeature.build_faiss_index()
            
            self.stdout.write(
                self.style.SUCCESS(f"인덱스 생성 완료: {index_path}")
            )
            self.stdout.write(
                self.style.SUCCESS(f"ID 매핑 파일: {id_path}")
            )
            
        except Exception as e:
            logger.error(f"FAISS 인덱스 빌드 실패: {str(e)}", exc_info=True)
