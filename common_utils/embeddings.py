# core/embeddings.py 또는 common_utils/embeddings.py

from sentence_transformers import SentenceTransformer
import numpy as np
import time # 모델 로딩 시간 확인용

# --- 모델 로딩 (애플리케이션 시작 시 한 번만 실행되도록 구성) ---
# 주의: 이 부분은 함수 호출 시마다 실행되면 매우 비효율적입니다.
#      모듈이 처음 임포트될 때 또는 Django AppConfig의 ready() 메소드 등에서
#      한 번만 로드되어야 합니다. 아래는 모듈 레벨에서 로드하는 예시입니다.

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"
print(f"임베딩 모델 로딩 시작: {MODEL_NAME}")
start_time = time.time()

try:
    # 모델을 전역 변수 등으로 로드하여 재사용합니다.
    # GPU 사용 가능 시 자동으로 GPU 사용
    embedding_model = SentenceTransformer(MODEL_NAME)
    print(f"임베딩 모델 로딩 완료! ({time.time() - start_time:.2f}초)")
except Exception as e:
    print(f"모델 로딩 중 오류 발생: {e}")
    embedding_model = None # 로딩 실패 시 None으로 설정

# --- 임베딩 함수 ---

def get_korean_text_embedding(sentence: str) -> list[float] | None:
    """
    주어진 한국어 문장을 사전 로드된 Sentence Transformer 모델을 사용하여
    고차원 벡터(임베딩)로 변환합니다.

    Args:
        sentence: 벡터로 변환할 한국어 문장 (string).

    Returns:
        문장의 임베딩 벡터 (list of float). 모델 로딩 실패 또는 에러 시 None 반환.
        벡터 크기는 모델에 따라 다름 (이 모델은 768차원).
    """
    global embedding_model # 로드된 모델 사용 명시

    if embedding_model is None:
        print("오류: 임베딩 모델이 로드되지 않았습니다.")
        return None

    if not isinstance(sentence, str) or len(sentence.strip()) == 0:
        print("경고: 입력 문장이 비어있거나 유효하지 않습니다.")
        # 빈 문자열 등에 대한 처리 정책 필요 (예: None 반환, 0 벡터 반환 등)
        return None

    try:
        # 모델의 encode 함수를 사용하여 임베딩 벡터 생성 (결과는 numpy array)
        vector = embedding_model.encode(sentence)
        # numpy array를 파이썬 리스트로 변환하여 반환
        return vector.tolist()
    except Exception as e:
        print(f"임베딩 생성 중 오류 발생: {e}")
        return None
