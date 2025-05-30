from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import json
from typing import Dict, List, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv
import os
from datetime import datetime

print("SentenceTransformer 모델(snunlp/KR-SBERT-V40K-klueNLI-augSTS)을 로드합니다...")
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
print("모델 로드 완료.")

print(".env 파일에서 환경 변수를 로드합니다...")
load_dotenv()
print("환경 변수 로드 시도 완료.")

print("OpenAI 클라이언트를 초기화합니다...")
client = OpenAI()
print("OpenAI 클라이언트 초기화 완료.")

# 중복 방지를 위한 timestamp 기반 저장 경로
def get_unique_output_paths(base_name: str = "spot") -> Dict[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "summary": f"output/{base_name}_summaries_{timestamp}.json",
        "index": f"output/{base_name}_index_{timestamp}.faiss",
        "id_map": f"output/{base_name}_id_map_{timestamp}.json"
    }

# 기존 요약 캐시 불러오기 (있으면)
def load_cached_summaries(path: str) -> Dict[str, str]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# 요약 결과 저장
def save_summaries(summaries: Dict[str, str], path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summaries, f, ensure_ascii=False, indent=2)

def parse_binary_flag(value: str, yes_text: str, no_text: str) -> str:
    if value == "1":
        return yes_text
    elif value == "0":
        return no_text
    return ""


def generate_intro_text(intro: Dict[str, Any], info: Dict[str, Any], cat_code: str) -> str:
    parts = []

    # 대표메뉴
    firstmenu = intro.get("firstmenu", "").strip()
    if firstmenu:
        parts.append(f"대표 메뉴는 {firstmenu}입니다.")

    parkingfood = intro.get("parkingfood", "").strip()
    if parkingfood:
        parts.append(f"주차장 여부는 {parkingfood}입니다.")

    usefee = intro.get("usefee", "").strip()
    if usefee:
        parts.append(f"이용 요금은 {usefee}입니다.")

    # 문화재 여부
    heritage_flags = [intro.get(f"heritage{i}", "0") for i in range(1, 4)]
    if "1" in heritage_flags:
        parts.append("문화재로 지정된 장소입니다.")

    # 유아시설, 유모차 대여
    kids_msg = parse_binary_flag(intro.get("kidsfacility", ""), "어린이 놀이방이 있습니다.", "어린이 놀이방은 없습니다.")
    if kids_msg:
        parts.append(kids_msg)
    bbq_msg = parse_binary_flag(intro.get("chkbabycarriage", ""), "유모차 대여가 가능합니다.", "유모차 대여는 불가능합니다.")
    if bbq_msg:
        parts.append(bbq_msg)

    # 카테고리 매핑
    category_map = {
        "AC": "숙박",
        "C01": "관광지",
        "EV": "관광지",
        "EX": "관광지",
        "FD": "음식점",
        "HS": "관광지",
        "LS": "레포츠",
        "NA": "관광지",
        "SH": "관광지",
        "VE": "문화시설"
    }

    cat_desc = category_map.get(cat_code, "")
    if cat_desc:
        parts.append(f"{cat_desc} 카테고리에 속한 장소입니다.")

    return " ".join(parts)



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
 주어진 필드에서 핵심 정보를 추출하고, 분위기, 방문 시기, 타깃, 액티비티, 혼잡도 등 숨은 매력도 보완해서 정체성, 위치, 매력, 즐길 거리, 대상층이 고루 드러나도록 30~40단어 이내 한 문장으로 요약
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


def combine_contentid_with_intro_info(common_file: str, info_map: Dict[str, dict], intro_map: Dict[str, dict]) -> Dict[str, str]:
    reorganized_data = {}
    print(f"'{common_file}' 파일에서 데이터를 로드하고 텍스트를 조합합니다...")

    try:
        with open(common_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        if not isinstance(data, list):
            print("  오류: JSON이 리스트 형식이 아닙니다.")
            return {}

        for item in data:
            content_id = str(item.get("contentid", "")).strip()
            title = str(item.get("title", "")).strip()
            overview = str(item.get("overview", "")).strip()
            cat_code = item.get("lclsSystm1", "")

            if not content_id:
                continue

            intro = intro_map.get(content_id, {})
            info = info_map.get(content_id, {})

            extra_info = generate_intro_text(intro, info, cat_code)
            full_text = f"{title} {overview} {extra_info}".strip()

            reorganized_data[content_id] = full_text

        print(f"  {len(reorganized_data)}개의 contentid에 대해 텍스트 조합 완료.")
    except Exception as e:
        print(f"combine_contentid_with_intro_info() 오류: {e}")

    return reorganized_data



def generate_gpt_summaries_from_file(common_file: str, info_file: str, intro_file: str, cache_path: Optional[str] = None) -> Dict[str, str]:
    print(f"\n📄 파일 기반 GPT 요약 생성을 시작합니다...")

    # 기존 요약 캐시 불러오기
    existing_summaries = load_cached_summaries(cache_path) if cache_path else {}
    print(f"  🗃️  기존 캐시에서 {len(existing_summaries)}개 요약 로드됨.")

    # JSON 데이터 로드
    with open(info_file, 'r', encoding='utf-8') as f:
        info_data = json.load(f)
    with open(intro_file, 'r', encoding='utf-8') as f:
        intro_data = json.load(f)

    info_map = {str(item["contentid"]): item for item in info_data if "contentid" in item}
    intro_map = {str(item["contentid"]): item for item in intro_data if "contentid" in item}

    combined_text_map = combine_contentid_with_intro_info(common_file, info_map, intro_map)
    if not combined_text_map:
        print("❌ 텍스트 조합 실패 또는 없음. 요약 중단.")
        return {}

    final_summaries = existing_summaries.copy()
    total_items = len(combined_text_map)
    print(f"  ✏️ 총 {total_items}개 중 GPT 호출 필요 {total_items - len(existing_summaries)}개")

    for idx, (content_id, text) in enumerate(combined_text_map.items()):
        print(f"  ({idx+1}/{total_items}) Content ID '{content_id}' 처리 중...")

        # 캐시에 존재하면 생략
        if content_id in existing_summaries:
            print("    ✅ 캐시 사용")
            continue

        summary = gpt_summarize(text)
        final_summaries[content_id] = summary

    # 생성된 전체 요약 저장
    if cache_path:
        save_summaries(final_summaries, cache_path)
        print(f"\n💾 모든 요약 저장 완료 → '{cache_path}'")

    return final_summaries

if __name__ == '__main__':
    print("\n--- 메인 스크립트 실행 시작 ---")
    input_data_file = 'data/spot_metadata.json'
    faiss_index_output_file = "data/spot_index.faiss" # 이 파일명은 타임스탬프 없이 고정해도 되고, 아래처럼 타임스탬프를 넣어도 됩니다.
    faiss_id_map_output_file = "data/spot_id_map.json" # 이 파일명도 마찬가지입니다.

    input_common_file = 'data/spot_metadata.json'
    input_info_file = 'data/spot_metadata.json'
    input_intro_file = 'data/spot_metadata.json'

    PERSISTENT_SUMMARY_CACHE_FILE = "data/persistent_spot_summaries.json"

    output_paths_for_run_specific_files = get_unique_output_paths("spot_run_output")

    print(f"요약 캐시 파일로 '{PERSISTENT_SUMMARY_CACHE_FILE}'을 사용합니다.")

    all_summaries_map = generate_gpt_summaries_from_file(
        input_common_file,
        input_info_file,
        input_intro_file,
        cache_path=PERSISTENT_SUMMARY_CACHE_FILE
    )
    print("\nOpenAI API 키를 확인합니다...")
    if not os.getenv("OPENAI_API_KEY"):
        print("  경고: OPENAI_API_KEY가 설정되지 않았습니다. GPT 요약이 실패할 수 있습니다.")
        print("  '.env' 파일에 키를 추가하거나 환경 변수로 설정해주세요.")
    else:
        api_key_suffix = os.getenv('OPENAI_API_KEY', '')[-4:] if len(os.getenv('OPENAI_API_KEY', '')) >= 4 else 'N/A'
        print(f"  OpenAI API Key가 로드되었습니다. (키의 일부: ...{api_key_suffix})")

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
    embeddings = model.encode(texts_for_embedding, convert_to_numpy=True, show_progress_bar=True)
    print("임베딩 생성 완료.")

    # 7. FAISS 인덱스 생성 및 저장
    if embeddings.ndim == 1:  # 단일 임베딩인 경우를 위해 차원 확장
        embeddings = np.expand_dims(embeddings, axis=0)

    if embeddings.shape[0] == 0:
        print("생성된 임베딩이 없습니다. FAISS 인덱스를 만들 수 없습니다.")
        exit()

    dimension = embeddings.shape[1]
    print(f"FAISS HNSW 인덱스를 생성합니다 (차원: {dimension})...")

    # HNSW 인덱스 생성 (M은 그래프에서 각 노드가 연결할 이웃 개수)
    index = faiss.IndexHNSWFlat(dimension, 32)

    # efSearch 파라미터 설정 (탐색 품질 조정용)
    index.hnsw.efSearch = 64  # 추천: 32~128 사이에서 튜닝

    index.add(embeddings)  # 임베딩 추가
    print("FAISS HNSW 인덱스에 임베딩 추가 완료.")

    # 인덱스 저장
    try:
        faiss.write_index(index, faiss_index_output_file)
        print(f"FAISS HNSW 인덱스를 '{faiss_index_output_file}' 파일로 성공적으로 저장했습니다.")
    except Exception as e:
        print(f"오류: FAISS 인덱스 '{faiss_index_output_file}' 저장 실패: {e}")
        exit()

    # contentid ↔ FAISS 인덱스 순서 매핑 저장
    print(f"FAISS 인덱스-ContentID 맵을 '{faiss_id_map_output_file}' 파일로 저장합니다...")
    try:
        with open(faiss_id_map_output_file, 'w', encoding='utf-8') as f:
            json.dump(ordered_content_ids_for_faiss_map, f, ensure_ascii=False, indent=2)
        print(f"FAISS 인덱스-ContentID 맵을 '{faiss_id_map_output_file}'에 저장했습니다.")
    except IOError as e:
        print(f"오류: FAISS ID 맵 '{faiss_id_map_output_file}' 저장 실패: {e}")

    print("\n--- 스크립트 실행 완료 ---")
