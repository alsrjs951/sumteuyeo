# management/commands/train_encoders.py
from django.core.management.base import BaseCommand
from apps.recommender.models import ContentDetailCommon
from sklearn.preprocessing import OneHotEncoder
import joblib
import os
import numpy as np

class Command(BaseCommand):
    help = "Train category encoders"
    
    def handle(self, *args, **kwargs):
        # 인코더 저장 경로 생성
        os.makedirs('encoders', exist_ok=True)
        
        # 계층별 매핑 정보 (필드명:인코더명)
        CATEGORY_MAPPING = {
            'lclssystm1': 'lcls1',
            'lclssystm2': 'lcls2',
            'lclssystm3': 'lcls3'
        }

        for model_field, encoder_name in CATEGORY_MAPPING.items():
            # 고유값 추출 (빈 값 필터링)
            values = ContentDetailCommon.objects.exclude(**{model_field: ''}) \
                                                .order_by(model_field) \
                                                .values_list(model_field, flat=True) \
                                                .distinct()
            
            if not values.exists():
                self.stdout.write(self.style.WARNING(f"No data found for {model_field}"))
                continue

            # 인코더 학습
            encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
            encoder.fit(np.array(values).reshape(-1, 1))
            
            # 파일 저장
            filename = f'encoders/{encoder_name}_encoder.joblib'
            joblib.dump(encoder, filename)
            self.stdout.write(self.style.SUCCESS(f"Created {filename} with {len(values)} categories"))

        self.stdout.write(self.style.SUCCESS("\nSuccessfully trained all category encoders"))
