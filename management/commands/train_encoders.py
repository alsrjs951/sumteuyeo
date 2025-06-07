# management/commands/train_encoders.py
from django.core.management.base import BaseCommand
from apps.recommender.models import ContentDetailCommon
import joblib
import os
import numpy as np

class Command(BaseCommand):
    help = "Train category embedding layers"
    
    def handle(self, *args, **kwargs):
        os.makedirs('encoders', exist_ok=True)
        
        CATEGORY_MAPPING = {
            'lclssystm1': 'lcls1',
            'lclssystm2': 'lcls2',
            'lclssystm3': 'lcls3'
        }

        EMBEDDING_DIM = 100  # 100차원 고정

        for model_field, encoder_name in CATEGORY_MAPPING.items():
            # 고유값 추출
            values = ContentDetailCommon.objects.exclude(**{model_field: ''}) \
                                                .values_list(model_field, flat=True) \
                                                .distinct()
            
            if not values:
                self.stdout.write(self.style.WARNING(f"No data found for {model_field}"))
                continue

            # 카테고리 → 정수 매핑 생성 (0번은 unknown용)
            unique_cats = sorted(list(set(values)))
            cat_to_idx = {cat: idx+1 for idx, cat in enumerate(unique_cats)}
            
            # 랜덤 임베딩 매트릭스 생성 (학습 없이 초기화)
            vocab_size = len(unique_cats)
            embedding_matrix = np.random.randn(vocab_size + 1, EMBEDDING_DIM)  # (n+1, 100)

            # 저장 데이터 구성
            encoder_data = {
                'mapping': cat_to_idx,
                'embedding_matrix': embedding_matrix,
                'unknown_index': 0  # 미확인 카테고리 처리용
            }

            # 파일 저장
            filename = f'encoders/{encoder_name}_encoder.joblib'
            joblib.dump(encoder_data, filename)
            self.stdout.write(
                self.style.SUCCESS(f"Created {filename} ({len(unique_cats)} categories → 100D)")
            )

        self.stdout.write(self.style.SUCCESS("\nSuccessfully trained all category encoders"))
