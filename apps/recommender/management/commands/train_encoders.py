from django.core.management.base import BaseCommand
from apps.items.models import ContentDetailCommon
from sklearn.preprocessing import OneHotEncoder
import joblib
import os
import json
import numpy as np
from pathlib import Path
from sumteuyeo.settings import BASE_DIR  # settings.py에서 BASE_DIR 임포트

class Command(BaseCommand):
    help = "Train category encoders and generate cat_dict.json"

    def handle(self, *args, **kwargs):
        # 절대 경로 설정 (프로젝트 루트/encoders)
        encoder_dir = Path(BASE_DIR) / 'encoders'
        encoder_dir.mkdir(parents=True, exist_ok=True)

        CATEGORY_MAPPING = {
            'lclssystm1': 'lcls1',
            'lclssystm2': 'lcls2',
            'lclssystm3': 'lcls3'
        }

        cat_dict = {}

        for model_field, encoder_name in CATEGORY_MAPPING.items():
            values = ContentDetailCommon.objects.exclude(**{model_field: ''}) \
                                                .order_by(model_field) \
                                                .values_list(model_field, flat=True) \
                                                .distinct()
            if not values.exists():
                self.stdout.write(self.style.WARNING(f"No data found for {model_field}"))
                continue

            values_list = list(values)
            
            # 1. OneHotEncoder 학습
            encoder = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
            encoder.fit(np.array(values_list).reshape(-1, 1))
            
            # 2. 매핑 정보 생성
            categories = encoder.categories_[0].tolist()
            cat_dict[encoder_name] = {
                category: idx for idx, category in enumerate(categories)
            }
            
            # 3. 임베딩 행렬 생성 (랜덤 초기화)
            embedding_dim = {
                'lcls1': 40,
                'lcls2': 30,
                'lcls3': 30
            }[encoder_name]

            categories_count = len(categories) + 1  # unknown 포함
            
            embedding_matrix = np.random.normal(
                scale=0.01, 
                size=(categories_count, embedding_dim)  # 레벨별 차원 적용
            ).astype(np.float32)
            
            # 4. 사용자 정의 데이터 저장
            encoder_data = {
                'encoder': encoder,
                'mapping': cat_dict[encoder_name],
                'unknown_index': len(categories),
                'embedding_matrix': embedding_matrix
            }
            
            # 5. 파일 저장 (절대 경로 사용)
            filename = encoder_dir / f'{encoder_name}_encoder.joblib'
            joblib.dump(encoder_data, filename)
            self.stdout.write(self.style.SUCCESS(f"Created {filename}"))

        # 6. cat_dict.json 저장 (절대 경로 사용)
        cat_dict_path = encoder_dir / 'cat_dict.json'
        with open(cat_dict_path, 'w', encoding='utf-8') as f:
            json.dump(cat_dict, f, ensure_ascii=False, indent=2)
            
        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully generated {cat_dict_path}"))
