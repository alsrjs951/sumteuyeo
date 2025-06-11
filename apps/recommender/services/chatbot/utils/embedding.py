import sys
import os
import re
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from asgiref.sync import sync_to_async
import faiss
from dotenv import load_dotenv
from bareunpy import Corrector


# --------------------------------------------------------------------------
# 1. 모델 및 데이터 로드 (API 키 로드 필수)
# --------------------------------------------------------------------------

# SentenceTransformer 모델 로드
print("Loading SentenceTransformer model (snunlp/KR-SBERT-V40K-klueNLI-augSTS)...")
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
print("SentenceTransformer model loaded.")

# [중요] API 키는 환경변수에서 가져옵니다.
load_dotenv()
BAREUN_API_KEY = os.getenv("BAREUN_API_KEY")
if not BAREUN_API_KEY:
    raise ValueError("[에러] BAREUN_API_KEY 환경 변수가 설정되지 않았습니다. API 키를 설정해주세요.")

# 바른 교정기 초기화 (로컬 서버 사용 시)
HOST = "localhost"   # 로컬 서버가 아니라면 bareun.ai 등으로 변경
PORT = 5656        # 포트는 서버 실행 환경에 따라 변경
corrector = Corrector(apikey=BAREUN_API_KEY, host=HOST, port=PORT)

# Faiss 인덱스 및 메타데이터 로드
current_file_dir = os.path.dirname(os.path.abspath(__file__))
chatbot_service_dir = os.path.dirname(current_file_dir)
data_dir = os.path.join(chatbot_service_dir, "data")
faiss_file_path = os.path.join(data_dir, "spot_index.faiss")
metadata_file_path = os.path.join(data_dir, "persistent_spot_summaries.json")
print(f"Reading Faiss index from: {faiss_file_path}")
faiss_index = faiss.read_index(faiss_file_path)
print(f"Reading metadata from: {metadata_file_path}")
with open(metadata_file_path, "r", encoding="utf-8") as f:
    spot_data = json.load(f)
print("\n--- All models and data loaded successfully. ---")

# --------------------------------------------------------------------------
# 2. 함수 정의 (bareunpy 라이브러리 사용)
# --------------------------------------------------------------------------

def correct_text_with_bareunpy(text: str) -> str:
    if not text.strip():
        return text

    try:
        response = corrector.correct_error(content=text)
        return response.revised
    except Exception as e:
        print(f"    - '바른' 맞춤법 교정 중 예외 발생: {e}")
        return text

def normalize_query(query: str) -> str:
    print(f"\n[1] Original Query: '{query}'")

    corrected_query = correct_text_with_bareunpy(query)
    print(f"[2] Spell Corrected (bareunpy): '{corrected_query}'")
    query = corrected_query

    # ... (이하 정규화 로직은 수정할 필요 없이 그대로 사용) ...
    query = query.lower()
    query = re.sub(r"[^가-힣a-z0-9\s]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    print(f"[3] Special Chars Removed & Trimmed: '{query}'")
    '''
    stopwords = [
        "추천해줘", "추천해", "추천좀", "추천할만한", "추천", "추천받고싶어", "추천부탁드려요", "추천바랍니다", "추천해주세요",
        "알려줘", "알려줄래", "알려줄수있어", "알려", "알려줘요", "알려주라", "알려주면", "알려주실", "알려주십쇼", "알려주세요",
        "찾아줘", "찾아줄래", "찾아", "찾아줘요", "찾아주라", "찾아주면", "찾아주실", "찾아주십쇼", "찾아주세요",
        "소개해줘", "소개해", "소개", "소개해줘요", "소개해주라", "소개해주면", "소개해주실", "소개해주십쇼", "소개해주세요",
        "어디", "어디야", "어디에", "어디서", "어디있는", "어디있는지", "어디로", "어디가", "어디가좋아", "어디갈까", "어디가야해",
        "좋은", "괜찮은", "가볼만한", "갈만한", "가고싶은", "가고싶다", "가고싶어", "가자", "가야할", "가면좋은", "가면좋을",
        "뭐가", "뭐야", "뭐있어", "뭐있나요", "뭐가좋아", "뭐가있어", "뭐가좋을까", "뭐가유명해", "뭐가맛있어", "뭐먹지", "뭐먹을까",
        "좀", "한번", "한 번", "궁금해", "궁금합니다", "궁금해요", "추천바람", "추천요청", "추천부탁", "부탁해", "부탁드립니다", "부탁해요", "부탁"
    ]
    query = ' '.join([word for word in query.split() if word not in stopwords])
    print(f"[4] Stopwords Removed: '{query}'")
    
    synonym_map = {"가볼만한 곳": "관광지", "숨은 명소": "조용한 장소", "힐링 스팟": "한적한 장소", "핫플": "인기 장소", }
    for k, v in synonym_map.items():
        query = query.replace(k, v)
    
    query = re.sub(r"\s+", " ", query).strip()
    '''
    print(f"[4] Final Normalized Query: '{query}'")

    return query

@sync_to_async
def embed_query(query):
    return model.encode([query])

@sync_to_async
def search_faiss(query_vec, top_n):
    # 검색 결과 개수를 top_n으로 직접 사용하고, 필요하다면 호출하는 쪽에서 top_n * 5 등으로 조절
    return faiss_index.search(query_vec, top_n)

def get_spot_data():
    return spot_data
