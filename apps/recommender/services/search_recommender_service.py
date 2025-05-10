from sentence_transformers import SentenceTransformer, util
import torch
import re
import openai
openai.api_key = "your-api-key"

# --- 문장 임베딩 모델 로드 (함수 외부에서 한 번 로드하는 것이 효율적) ---
try:
    embedding_model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
    print("Sentence Embedding Model 로드 완료.")
except Exception as e:
    print(f"모델 로드 중 오류 발생: {e}")
    print("sentence-transformers 및 torch 라이브러리가 설치되었는지 확인하세요 (`pip install sentence-transformers torch`).")
    embedding_model = None #

#pt햄 요약만들기 (api키 따와서 변경할 예정)
'''def gpt_summarize(text: str, max_tokens: int = 300) -> str:
    """
    GPT API를 사용해 주어진 텍스트를 요약합니다.

    Args:
        text: 원본 텍스트
        max_tokens: 생성되는 요약문의 최대 토큰 수

    Returns:
        요약된 문자열
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # 또는 "gpt-4"
            messages=[
                {"role": "system", "content": "당신은 유용하고 간결한 요약을 잘하는 비서입니다."},
                {"role": "user", "content": f"다음 텍스트를 간결하고 핵심만 담은 2~4문장으로 요약해줘:\n\n{text}"}
            ],
            temperature=0.5,
            max_tokens=max_tokens
        )
        summary = response['choices'][0]['message']['content'].strip()
        return summary
    except Exception as e:
        print(f"GPT 요약 중 오류 발생: {e}")
        return ""
'''

# --- 간단한 텍스트 요약 함수 (예시 목적) --- < 이 함수 부분을 gpt api 사용
def simple_extractive_summarize(text: str, num_sentences: int = 2) -> str:
    """
    입력 텍스트에서 처음 N개의 문장을 추출하여 요약합니다.
    이는 매우 기본적인 요약 방식이며 실제 요약 모델이 아닙니다.

    Args:
        text: 요약할 원본 텍스트.
        num_sentences: 추출할 문장의 개수.

    Returns:
        추출된 문장들을 합친 문자열. 입력 텍스트가 없으면 빈 문자열.
    """
    if not text or not isinstance(text, str):
        return ""

    # 한글 문장 부호(. ! ?) 뒤 공백을 기준으로 문장 분리 (간단한 방식)
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    # 처음 num_sentences 개 문장 선택
    summary_sentences = sentences[:num_sentences]

    # 선택된 문장들을 공백으로 연결하여 반환
    return " ".join(summary_sentences).strip()

def get_summarized_tourism_embedding(tourism_info_text: str, model: SentenceTransformer | None) -> torch.Tensor | None:
    """
    관광지 정보 텍스트를 입력받아 간단히 요약하고,
    요약된 텍스트의 문장 임베딩 벡터를 반환하는 함수.

    Args:
        tourism_info_text: 관광지에 대한 원본 설명 텍스트.
        model: 로드된 SentenceTransformer 모델 객체. 모델 로드 실패 시 None일 수 있음.

    Returns:
        요약된 텍스트의 임베딩 벡터 (PyTorch Tensor),
        또는 입력 텍스트가 없거나 모델 로드 실패, 요약 실패 시 None.
    """
    if model is None:
        print("Sentence Embedding 모델이 로드되지 않았습니다. 임베딩을 수행할 수 없습니다.")
        return None

    if not tourism_info_text or not isinstance(tourism_info_text, str):
        print("입력 텍스트가 비어있거나 유효하지 않습니다.")
        return None

    # --- 1단계: 관광지 정보 요약 ---
    print("\n--- 요약 과정 ---")
    summarized_text = simple_extractive_summarize(tourism_info_text, num_sentences=2)

    if not summarized_text:
        print("요약된 내용이 비어있습니다. 임베딩을 생성할 수 없습니다.")
        return None

    print(f"원본 텍스트 (일부): {tourism_info_text[:100]}...")
    print(f"요약된 텍스트: '{summarized_text}'")

    # --- 2단계: 요약된 텍스트를 임베딩 ---
    try:
        summarized_embedding = model.encode(summarized_text, convert_to_tensor=True)
        print("요약된 텍스트 임베딩 생성 완료.")
        return summarized_embedding
    except Exception as e:
        print(f"임베딩 생성 중 오류 발생: {e}")
        return None

if __name__ == "__main__":
    # 예시 관광지 정보 텍스트
    example_tourism_info = """
    내원사는 부산광역시 금정구에 위치한 아름다운 사찰입니다.
    천성산 자락에 자리하여 맑고 깨끗한 자연 환경을 자랑합니다.
    특히 여름철에는 시원한 계곡물이 흘러 많은 사람들이 피서를 위해 찾습니다.
    가을 단풍 또한 매우 유명하여 사진 작가들의 발길이 끊이지 않습니다.
    조용하고 평화로운 분위기 속에서 산책을 하거나 사찰 체험을 할 수 있습니다.
    문화재로 지정된 대웅전과 삼성각 등 유서 깊은 건축물들을 둘러보는 것도 좋습니다.
    도심에서 멀지 않아 접근성이 좋으며, 넓은 주차 공간도 마련되어 있습니다.
    자연 속에서 휴식과 힐링을 경험하고 싶은 분들에게 강력 추천하는 곳입니다.
    주변에 맛집과 카페들도 있어 함께 즐기기 편리합니다.
    """

    if embedding_model:
        summarized_embedding_vector = get_summarized_tourism_embedding(example_tourism_info, embedding_model)

        if summarized_embedding_vector is not None:
            print("\n--- 최종 결과 ---")
            print("생성된 요약 임베딩 벡터 형태:", summarized_embedding_vector.shape)

            # 예시: 사용자 질의와의 유사도 비교
            query_sentence = "제주도에서 귤 따고싶어"
            try:
                query_embedding = embedding_model.encode(query_sentence, convert_to_tensor=True)
                similarity = util.cos_sim(query_embedding, summarized_embedding_vector)
                print(f"\n사용자 질의: '{query_sentence}'")
                print(f"요약 임베딩과 질의 임베딩 간 코사인 유사도: {similarity.item()}")
            except Exception as e:
                 print(f"질의 임베딩 또는 유사도 계산 중 오류 발생: {e}")

        else:
            print("\n요약 임베딩 벡터 생성에 실패했습니다.")
    else:
         print("\n모델 로드 실패로 함수를 실행할 수 없습니다.")