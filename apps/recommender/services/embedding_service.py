from sentence_transformers import SentenceTransformer
import numpy as np

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"

try:
    embedding_model = SentenceTransformer(MODEL_NAME)
except Exception as e:
    print(f"모델 로딩 중 오류 발생: {e}")
    embedding_model = None # 로딩 실패 시 None으로 설정


# 주의: 최대한 호출 횟수를 줄이기 (연산량이 많음)
def get_korean_text_embedding(sentence: str) -> list[float] | None:
    global embedding_model

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
