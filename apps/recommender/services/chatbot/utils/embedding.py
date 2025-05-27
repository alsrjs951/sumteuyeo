import faiss
import json
import os
import numpy as np
from sentence_transformers import SentenceTransformer
from asgiref.sync import sync_to_async
from django.conf import settings # Django 설정을 사용하기 위해 추가

# SentenceTransformer 모델 로드
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")

# 현재 파일(embedding.py)이 있는 디렉토리
# 예: C:\Users\User\Desktop\django\sumteuyeo\apps\recommender\services\chatbot\utils
current_file_dir = os.path.dirname(os.path.abspath(__file__))

# chatbot 서비스 디렉토리 (utils 폴더의 부모)
# 예: C:\Users\User\Desktop\django\sumteuyeo\apps\recommender\services\chatbot
chatbot_service_dir = os.path.dirname(current_file_dir)

# Faiss 인덱스 파일 경로 구성
# 예: C:\Users\User\Desktop\django\sumteuyeo\apps\recommender\services\chatbot\data\spot_index.faiss
faiss_file_path = os.path.join(chatbot_service_dir, "data", "spot_index.faiss")

# JSON 메타데이터 파일 경로 구성
# 예: C:\Users\User\Desktop\django\sumteuyeo\apps\recommender\services\chatbot\data\spot_metadata.json
metadata_file_path = os.path.join(chatbot_service_dir, "data", "spot_metadata.json")

# 디버깅을 위해 실제 경로 출력 (서버 실행 시 터미널에서 확인 가능)
print(f"Attempting to read Faiss index from: {faiss_file_path}")
print(f"Attempting to read metadata from: {metadata_file_path}")

# Faiss 인덱스 로드
if not os.path.exists(faiss_file_path):
    raise FileNotFoundError(
        f"Faiss index file NOT FOUND at: {faiss_file_path}. "
        f"Please ensure the file exists at this location or check your path construction logic."
    )
else:
    print(f"Faiss index file FOUND at: {faiss_file_path}")
faiss_index = faiss.read_index(faiss_file_path)

# 메타데이터 로드
if not os.path.exists(metadata_file_path):
    raise FileNotFoundError(
        f"Metadata JSON file NOT FOUND at: {metadata_file_path}. "
        f"Please ensure the file exists at this location or check your path construction logic."
    )
else:
    print(f"Metadata JSON file FOUND at: {metadata_file_path}")
with open(metadata_file_path, "r", encoding="utf-8") as f: # "r" 모드 명시 및 utf-8 인코딩 유지
    spot_data = json.load(f)

@sync_to_async
def embed_query(query):
    return model.encode([query])

@sync_to_async
def search_faiss(query_vec, top_n):
    # 검색 결과 개수를 top_n으로 직접 사용하고, 필요하다면 호출하는 쪽에서 top_n * 5 등으로 조절
    return faiss_index.search(query_vec, top_n)

def get_spot_data():
    return spot_data