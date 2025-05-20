from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os

print("SentenceTransformer 모델(snunlp/KR-SBERT-V40K-klueNLI-augSTS)을 로드합니다...")
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
print("모델 로드 완료.")

print(".env 파일에서 환경 변수를 로드합니다...")
load_dotenv()
print("환경 변수 로드 시도 완료.")

print("OpenAI 클라이언트를 초기화합니다...")
client = OpenAI()
print("OpenAI 클라이언트 초기화 완료.")

def gpt_summarize(text: str) -> str:
    if not text.strip():  # 내용 없는 텍스트는 API 호출 방지
        print("  요약할 텍스트가 비어있어 GPT 호출을 건너뜁니다.")
        return ""
    try:
        response = client.chat.completions.create(  # 전역 client 변수 사용
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 ‘관광지 종합 요약 엔진’입니다."},
                {"role": "user", "content": f"""
 주어진 필드에서 핵심 정보를 추출하고, 분위기, 방문 시기, 타깃, 액티비티, 혼잡도 등 숨은 매력도 보완해서 정체성, 위치, 매력, 즐길 거리, 대상층이 고루 드러나도록 20~30단어 이내 한 문장으로 요약
텍스트: {text}
"""}
            ],
            temperature=0.5,
            max_tokens=300
        )
        summary = response.choices[0].message.content if hasattr(response.choices[0].message, 'content') else \
            response.choices[0].message.get('content')

        summary = summary.strip() if summary else ""
        return summary
    except Exception as e:
        print(f"  GPT 호출 중 오류 발생 (텍스트 앞부분: '{text[:50]}...'): {e}")
        return ""


def combine_contentid(file_path: str) -> Dict[str, str]:
    reorganized_data: Dict[str, str] = {}
    print(f"'{file_path}' 파일에서 데이터를 로드하고 텍스트를 조합합니다...")
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data_from_file: Any = json.load(f)

        if not isinstance(data_from_file, list):
            print(f"  경고: '{file_path}' 파일의 JSON 내용이 리스트가 아닙니다. 아이템 리스트를 예상했습니다.")
            return reorganized_data

        data_list_to_process: List[Any] = data_from_file
        print(f"  총 {len(data_list_to_process)}개의 아이템을 발견했습니다.")

        item_count = 0
        for item in data_list_to_process:
            item_count += 1
            if not isinstance(item, dict):
                print(f"  경고 (아이템 {item_count}): 딕셔너리가 아닌 아이템을 건너뜁니다: {item}")
                continue

            content_id: Optional[str] = item.get("contentid")
            title_value: Optional[str] = item.get("title")
            overview_value: Optional[str] = item.get("overview")

            if content_id is not None:
                title_str = str(title_value) if title_value is not None else ""
                overview_str = str(overview_value) if overview_value is not None else ""
                combined_text = (title_str + " " + overview_str).strip()
                reorganized_data[str(content_id)] = combined_text
            else:
                item_title_for_warning = str(title_value) if title_value is not None else "타이틀 없음"
                print(f"  경고 (아이템 {item_count}): 'contentid'가 없는 아이템을 발견했습니다 (타이틀: '{item_title_for_warning}').")
        print(f"  텍스트 조합 완료. {len(reorganized_data)}개의 유효한 contentid 항목 처리됨.")
    except FileNotFoundError:
        print(f"  오류: '{file_path}' 경로에서 파일을 찾을 수 없습니다.")
    except json.JSONDecodeError:
        print(f"  오류: '{file_path}' 파일에서 JSON을 디코딩할 수 없습니다.")
    except Exception as e:
        print(f"  combine_contentid 함수에서 예상치 못한 오류가 발생했습니다: {e}")

    return reorganized_data


def generate_gpt_summaries_from_file(file_path: str) -> Dict[str, str]:
    print(f"\n'{file_path}' 파일을 기반으로 GPT 요약 생성을 시작합니다...")

    contentid_to_combined_text = combine_contentid(file_path)

    if not contentid_to_combined_text:
        print("파일에서 처리할 텍스트 데이터를 찾지 못했거나 생성하지 못했습니다. 요약 작업을 중단합니다.")
        return {}

    final_summaries: Dict[str, str] = {}
    total_items = len(contentid_to_combined_text)
    print(f"  총 {total_items}개의 항목에 대해 GPT 요약을 시도합니다...")

    for current_item_index, (content_id, combined_text) in enumerate(contentid_to_combined_text.items()):
        print(f"  ({current_item_index + 1}/{total_items}) Content ID '{content_id}' 요약 중...")

        if not combined_text:
            print(f"    Content ID '{content_id}'의 조합된 텍스트가 비어있어 요약을 건너뜁니다.")
            final_summaries[content_id] = ""
            continue

        summary = gpt_summarize(combined_text)

        if summary:
            final_summaries[content_id] = summary
            print(f"    Content ID '{content_id}' 요약 완료.")
        else:
            print(f"    Content ID '{content_id}'에 대한 요약 생성에 실패했거나 빈 요약이 반환되었습니다.")
            final_summaries[content_id] = ""

    print("모든 항목에 대한 요약 시도가 완료되었습니다.")
    return final_summaries


# --- 메인 실행 블록 ---
if __name__ == '__main__':
    print("\n--- 메인 스크립트 실행 시작 ---")
    input_data_file = 'data/spot_metadata.json'
    faiss_index_output_file = "data/spot_index.faiss"
    faiss_id_map_output_file = "data/spot_id_map.json"

    print("\nOpenAI API 키를 확인합니다...")
    if not os.getenv("OPENAI_API_KEY"):
        print("  경고: OPENAI_API_KEY가 설정되지 않았습니다. GPT 요약이 실패할 수 있습니다.")
        print("  '.env' 파일에 키를 추가하거나 환경 변수로 설정해주세요.")
    else:
        api_key_suffix = os.getenv('OPENAI_API_KEY', '')[-4:] if len(os.getenv('OPENAI_API_KEY', '')) >= 4 else 'N/A'
        print(f"  OpenAI API Key가 로드되었습니다. (키의 일부: ...{api_key_suffix})")

    all_summaries_map = generate_gpt_summaries_from_file(input_data_file)  # 반환: Dict[contentid, summary_string]

    if not all_summaries_map:
        print("\n생성된 요약이 없어 FAISS 인덱싱을 진행할 수 없습니다. 스크립트를 종료합니다.")
        exit()

    # 5. FAISS 인덱싱을 위한 텍스트 준비 (생성된 GPT 요약 사용)
    # FAISS 인덱스의 순서와 contentid를 매핑하기 위해 일관된 순서가 필요
    # contentid를 기준으로 정렬하여 사용합니다.
    print("\nFAISS 인덱싱을 위한 텍스트(요약본)를 준비합니다...")

    sorted_content_ids = sorted(all_summaries_map.keys())

    texts_for_embedding: List[str] = []
    ordered_content_ids_for_faiss_map: List[str] = []

    for cid in sorted_content_ids:
        summary = all_summaries_map.get(cid, "")
        if summary and summary.strip():
            texts_for_embedding.append(summary)
            ordered_content_ids_for_faiss_map.append(cid)
        else:
            print(f"  Content ID '{cid}'의 요약이 비어있거나 없어 FAISS 인덱싱에서 제외됩니다.")

    if not texts_for_embedding:
        print("임베딩할 요약 텍스트가 없습니다. FAISS 인덱싱을 중단합니다.")
        exit()

    print(f"  총 {len(texts_for_embedding)}개의 유효한 요약에 대해 임베딩을 생성합니다...")

    # 6. 임베딩 생성
    # model 변수는 스크립트 상단에서 SentenceTransformer로 초기화되었습니다.
    embeddings = model.encode(texts_for_embedding, convert_to_numpy=True, show_progress_bar=True)
    print("임베딩 생성 완료.")

    # 7. FAISS 인덱스 생성 및 저장
    if embeddings.ndim == 1:  # 단일 임베딩인 경우를 위해 차원 확장 (보통은 2D 배열)
        embeddings = np.expand_dims(embeddings, axis=0)

    if embeddings.shape[0] == 0:  # 임베딩 결과가 없는 경우
        print("생성된 임베딩이 없습니다. FAISS 인덱스를 만들 수 없습니다.")
        exit()

    dimension = embeddings.shape[1]
    print(f"FAISS 인덱스를 생성합니다 (차원: {dimension})...")
    index = faiss.IndexFlatL2(dimension)  # L2 거리(유클리드 거리) 기반의 기본 인덱스
    index.add(embeddings)  # 생성된 임베딩들을 인덱스에 추가
    print("FAISS 인덱스에 임베딩 추가 완료.")

    try:
        faiss.write_index(index, faiss_index_output_file)
        print(f"FAISS 인덱스를 '{faiss_index_output_file}' 파일로 성공적으로 저장했습니다.")
    except Exception as e:
        print(f"오류: FAISS 인덱스 '{faiss_index_output_file}' 저장 실패: {e}")
        exit()

    # 8. FAISS 인덱스 순서와 contentid 매핑 정보 저장
    # 이 맵은 FAISS 검색 결과(숫자 인덱스)를 실제 contentid로 변환하는 데 사용됩니다.
    print(f"FAISS 인덱스-ContentID 맵을 '{faiss_id_map_output_file}' 파일로 저장합니다...")
    try:
        with open(faiss_id_map_output_file, 'w', encoding='utf-8') as f:
            json.dump(ordered_content_ids_for_faiss_map, f, ensure_ascii=False, indent=2)
        print(f"FAISS 인덱스-ContentID 맵을 '{faiss_id_map_output_file}'에 저장했습니다.")
    except IOError as e:
        print(f"오류: FAISS ID 맵 '{faiss_id_map_output_file}' 저장 실패: {e}")

    print("\n--- 스크립트 실행 완료 ---")