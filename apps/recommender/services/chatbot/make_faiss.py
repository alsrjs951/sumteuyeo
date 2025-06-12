'''from sentence_transformers import SentenceTransformer
import numpy as np
import json
from typing import Dict, List, Any, Optional, Tuple
from openai import OpenAI
from dotenv import load_dotenv
import os
from datetime import datetime
import time
from constants import cat_dict

print("SentenceTransformer 모델(snunlp/KR-SBERT-V40K-klueNLI-augSTS)을 로드합니다...")
model = SentenceTransformer("snunlp/KR-SBERT-V40K-klueNLI-augSTS")
print("모델 로드 완료.")

print(".env 파일에서 환경 변수를 로드합니다...")
load_dotenv()
print("환경 변수 로드 시도 완료.")

print("OpenAI 클라이언트를 초기화합니다...")
client = OpenAI()
print("OpenAI 클라이언트 초기화 완료.")

# GPT API 호출 배치 크기 (한 번에 몇 개를 요약할지)
# 이 값은 실험을 통해 최적값을 찾아야 합니다.
# 너무 크면 토큰 제한에 걸리거나 API 응답이 불안정할 수 있습니다.
# 너무 작으면 API 호출 횟수가 많아집니다.
GPT_BATCH_SIZE = 4  # 예시: 한 번에 7개씩 처리
GPT_REQUEST_DELAY_SECONDS = 1  # API 요청 간 최소 딜레이 (RateLimitError 방지)


# 중복 방지를 위한 timestamp 기반 저장 경로
def get_unique_output_paths(base_name: str = "spot") -> Dict[str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return {
        "summary": f"data/{base_name}_summaries_{timestamp}.json",
        "index": f"data/{base_name}_index_{timestamp}.faiss",
        "id_map": f"data/{base_name}_id_map_{timestamp}.json"
    }


# 기존 요약 캐시 불러오기 (있으면)
def load_cached_summaries(path: str) -> Dict[str, str]:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"  ⚠️ 경고: 캐시 파일 '{path}'이 비어있거나 유효한 JSON이 아닙니다. 빈 캐시로 시작합니다.")
                return {}
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

    firstmenu = intro.get("firstmenu", "").strip()
    if firstmenu:
        parts.append(f"대표 메뉴는 {firstmenu}입니다.")

    parkingfood = intro.get("parkingfood", "").strip()
    if parkingfood:
        parts.append(f"주차 여부는 {parkingfood}입니다.")

    heritage_flags = [intro.get(f"heritage{i}", "0") for i in range(1, 4)]
    if "1" in heritage_flags:
        parts.append("문화재로 지정된 장소입니다.")

    kids_msg = parse_binary_flag(intro.get("kidsfacility", ""), "어린이 놀이방이 있습니다.", "어린이 놀이방은 없습니다.")
    if kids_msg:
        parts.append(kids_msg)
    bbq_msg = parse_binary_flag(intro.get("chkbabycarriage", ""), "유모차 대여가 가능합니다.", "유모차 대여는 불가능합니다.")
    if bbq_msg:
        parts.append(bbq_msg)


    cat_desc = cat_dict.get(cat_code, "")
    if cat_desc:
        parts.append(f"{cat_desc} 카테고리에 속한 장소입니다.")

    return " ".join(parts)


def gpt_summarize_batch(items_to_summarize: List[Dict[str, str]]) -> Dict[str, str]:
    if not items_to_summarize:
        return {}

    # GPT에 전달할 입력 문자열 생성
    # 각 항목을 식별자와 함께 명확히 구분하여 전달
    prompt_input_parts = []
    for item in items_to_summarize:
        prompt_input_parts.append(
            f'{{"id": "{item["id"]}", "text": "{item["text"].replace("\"", "'")}"}}')  # JSON 내부에 들어갈 것이므로 text 내 "를 '로 치환

    # JSON 배열 형태로 입력 텍스트 구성
    input_json_array_string = "[" + ",\n".join(prompt_input_parts) + "]"

    # gpt_summarize_batch 함수 내에서 user_prompt 수정

    system_prompt = "당신은 ‘관광지 종합 요약 엔진’입니다. 여러 장소 설명을 입력받아 각 장소에 대한 요약문을 JSON 형식으로 반환합니다."
    user_prompt = f"""
    아래 장소 설명 텍스트를 기반으로
    각 장소에 대해 다음 기준에 따라 **40~50단어 내외의 장소 요약 문장**을 생성하세요:
    1. 장소 종류, 음식 종류 또는, 서비스 카테고리, 주차 여부를 **명확히 명시**할 것.
    2. **정체성(분위기/특색)**, **위치/접근성**, **대표 콘텐츠(메뉴/전시/체험)**, **대상층(연인/가족/반려동물 등)** 등을 고루 표현하고 **추천 방문 시기, 한적도** 등을 자연스럽고 감성적인 **대상 맞춤 추천 문장**으로 표현할 것. 만약 제공된 메타데이터가 부족할 경우, 모델이 학습한 일반 지식을 바탕으로 보충할 것.
    3. 불필요한 중복은 제거하되, 검색 가능성을 위해 **핵심 키워드**는 포함할 것.
    4. 마치 관광지 추천 플랫폼에서 추천 문구로 쓰이는 자연스러운 어조로 작성할 것.
    예) "제주 서쪽 송악산 인근의 송악산둘레길은 봄~가을 걷기 좋은 화산 트레일로, 연인, 가족과 반려동물 동반 산책객에게 적합한 한적한 코스입니다" 
    
    결과는 "summaries"라는 키를 가진 JSON 객체로 반환해주세요. "summaries" 키의 값은 각 장소의 'id'와 'summary'를 포함하는 객체들의 배열이어야 합니다.
    예시: `{{"summaries": [{{"id": "입력_ID_1", "summary": "요약문1"}}, {{"id": "입력_ID_2", "summary": "요약문2"}}, ...]}}`

    입력 JSON 배열:
    {input_json_array_string}

    요약 결과 JSON 객체:
    """
    print(f"  GPT API 호출: {len(items_to_summarize)}개 항목 요약 요청...")
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",  # 또는 gpt-4-turbo 등 사용 가능 모델
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=150 * len(items_to_summarize) + 500,  # 각 요약당 약 100~150 토큰 + JSON 구조 토큰 고려
            response_format={"type": "json_object"}  # GPT가 JSON을 반환하도록 요청 (최신 모델 지원)
            # 만약 이 옵션이 지원 안되면, 프롬프트에서 JSON을 잘 생성하도록 더 강조해야 함.
        )

        raw_response_content = response.choices[0].message.content
        # GPT가 JSON "블록" (```json ... ```)으로 반환하는 경우가 있어 이를 제거
        if raw_response_content.strip().startswith("```json"):
            raw_response_content = raw_response_content.strip()[7:-3].strip()

        # GPT 응답이 "summaries" 등의 키 아래 배열을 포함하는 경우 처리 (response_format을 쓰면 보통 바로 배열이 옴)
        # 예: {"summaries": [{"id": "1", "summary": "..."}]}
        # 또는 바로 배열: [{"id": "1", "summary": "..."}]
        summaries_dict = {}

        parsed_response = json.loads(raw_response_content)

        # 응답이 {'results': [...]} 또는 {'summaries': [...]} 등 다양한 형태일 수 있음
        # 가장 유력한 키를 찾아보거나, 직접 배열인지 확인
        if isinstance(parsed_response, list):
            results_array = parsed_response
        elif isinstance(parsed_response, dict):
            # 일반적인 키들을 찾아봄
            possible_keys = ['summaries', 'results', 'data', 'items']
            found_key = None
            for key in possible_keys:
                if key in parsed_response and isinstance(parsed_response[key], list):
                    found_key = key
                    break
            if found_key:
                results_array = parsed_response[found_key]
            else:  # 못찾으면 그냥 최상위 딕셔너리의 값들 중 리스트를 찾아봄 (덜 안정적)
                results_array = next((v for v in parsed_response.values() if isinstance(v, list)), None)
        else:
            results_array = None

        if results_array is None:
            print(f"  ⚠️ GPT 응답에서 요약 배열을 찾지 못했습니다. 응답: {raw_response_content[:200]}...")
            return {}

        for item in results_array:
            if isinstance(item, dict) and "id" in item and "summary" in item:
                summaries_dict[str(item["id"])] = str(item["summary"]).strip()
            else:
                print(f"  ⚠️ GPT 응답의 일부 항목이 올바르지 않은 형식입니다: {item}")

        print(f"  ✅ GPT로부터 {len(summaries_dict)}/{len(items_to_summarize)}개 요약 수신 완료.")
        return summaries_dict

    except json.JSONDecodeError as e:
        print(f"  ❌ GPT 응답 JSON 파싱 오류: {e}")
        print(f"  Raw GPT response: {raw_response_content[:500]}...")  # 너무 길면 잘라서 표시
        return {}
    except Exception as e:
        print(
            f"  ❌ GPT API 호출 중 오류 발생 (첫 항목 ID: '{items_to_summarize[0]['id'] if items_to_summarize else 'N/A'}'): {e}")
        return {}


def combine_contentid_with_intro_info(common_file: str, info_map: Dict[str, dict], intro_map: Dict[str, dict]) -> Dict[
    str, str]:
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
            # lclsSystm1는 1depth, lclsSystm2는 2depth, lclsSystm3은 3depth 카테고리 코드
            cat_code = item.get("lclsSystm3", "")

            if not content_id:
                continue

            intro = intro_map.get(content_id, {})
            info = info_map.get(content_id, {})

            extra_info = generate_intro_text(intro, info, cat_code)
            # 제목과 개요가 없으면 GPT에 보낼 필요가 없음
            if not title and not overview:
                full_text = extra_info.strip()
            else:
                full_text = f"이곳은 '{title}'입니다. {overview} {extra_info}".strip()

            if full_text:  # 비어있지 않은 텍스트만 추가
                reorganized_data[content_id] = full_text

        print(f"  {len(reorganized_data)}개의 contentid에 대해 텍스트 조합 완료.")
    except Exception as e:
        print(f"combine_contentid_with_intro_info() 오류: {e}")

    return reorganized_data


def generate_gpt_summaries_from_file(common_file: str, info_file: str, intro_file: str,
                                     cache_path: Optional[str] = None) -> Dict[str, str]:
    print(f"\n📄 파일 기반 GPT 요약 생성을 시작합니다...")

    existing_summaries = load_cached_summaries(cache_path) if cache_path else {}
    print(f"  🗃️  기존 캐시에서 {len(existing_summaries)}개 요약 로드됨.")

    with open(info_file, 'r', encoding='utf-8') as f_info:
        info_data_list = json.load(f_info)
    with open(intro_file, 'r', encoding='utf-8') as f_intro:
        intro_data_list = json.load(f_intro)

    # 데이터가 리스트가 아닐 경우 빈 리스트로 처리하여 오류 방지
    if not isinstance(info_data_list, list): info_data_list = []
    if not isinstance(intro_data_list, list): intro_data_list = []

    info_map = {str(item["contentid"]): item for item in info_data_list if
                isinstance(item, dict) and "contentid" in item}
    intro_map = {str(item["contentid"]): item for item in intro_data_list if
                 isinstance(item, dict) and "contentid" in item}

    combined_text_map = combine_contentid_with_intro_info(common_file, info_map, intro_map)
    if not combined_text_map:
        print("❌ 텍스트 조합 실패 또는 없음. 요약 중단.")
        return existing_summaries  # 기존 캐시라도 반환
    print(combined_text_map)
    final_summaries = existing_summaries.copy()

    items_to_process_api = []
    for content_id, text in combined_text_map.items():
        # 핵심 텍스트(overview 등)가 실제로 있는지 체크
        has_main_text = bool(text and text.strip())

        # 이미 요약이 되어 있거나, "텍스트 없음" 마커가 있으면 건너뜀
        already_summarized = (
                content_id in final_summaries and
                final_summaries[content_id].strip() and
                final_summaries[content_id] != "__NO_TEXT__"
        )

        if already_summarized:
            continue

        if has_main_text:
            items_to_process_api.append({"id": content_id, "text": text})
        else:
            print(f"  Content ID '{content_id}'의 텍스트가 없어 요약을 영구적으로 건너뜁니다.")
            final_summaries[content_id] = "__NO_TEXT__"  # 영구 skip 마커

    total_to_api = len(items_to_process_api)
    print(f"  ✏️ 총 {len(combined_text_map)}개 항목 중 GPT API 호출 필요: {total_to_api}개 (배치 크기: {GPT_BATCH_SIZE})")

    processed_count = 0
    for i in range(0, total_to_api, GPT_BATCH_SIZE):
        batch = items_to_process_api[i:i + GPT_BATCH_SIZE]
        if not batch:
            continue

        print(
            f"\n  처리 중인 배치: {i // GPT_BATCH_SIZE + 1} / {(total_to_api + GPT_BATCH_SIZE - 1) // GPT_BATCH_SIZE} (항목 {i + 1}~{min(i + GPT_BATCH_SIZE, total_to_api)})")

        batch_summaries = gpt_summarize_batch(batch)

        for item in batch:  # 배치에 포함된 모든 항목에 대해
            cid = item["id"]
            if cid in batch_summaries:
                final_summaries[cid] = batch_summaries[cid]
                print(f"    Content ID '{cid}': 요약 생성됨.")
            else:
                # API 호출에서 이 ID에 대한 요약이 반환되지 않은 경우 (오류 또는 누락)
                final_summaries[cid] = ""  # 빈 요약으로 처리, 나중에 다시 시도 안하도록
                print(f"    ⚠️ Content ID '{cid}': 배치 처리 후 요약 얻지 못함. 빈 요약으로 저장.")

        processed_count += len(batch)

        # 중간 저장 (선택 사항, 하지만 긴 작업에는 유용)
        if cache_path and processed_count % (GPT_BATCH_SIZE * 5) == 0:  # 예: 5 배치마다 저장
            save_summaries(final_summaries, cache_path)
            print(f"  💾 중간 요약 저장 완료 ({processed_count}/{total_to_api} 처리) → '{cache_path}'")

        # API Rate Limit을 피하기 위한 딜레이
        if i + GPT_BATCH_SIZE < total_to_api:  # 마지막 배치가 아니면
            print(f"  ⏳ 다음 API 요청 전 {GPT_REQUEST_DELAY_SECONDS}초 대기...")
            time.sleep(GPT_REQUEST_DELAY_SECONDS)

    if cache_path:
        save_summaries(final_summaries, cache_path)
        print(f"\n💾 모든 요약 저장 완료 → '{cache_path}'")

    return final_summaries


if __name__ == '__main__':
    print("\n--- 메인 스크립트 실행 시작 ---")
    # 입력 파일 경로들 - 실제 환경에 맞게 수정해야 합니다.
    # 현재는 모두 'spot_metadata.json'을 사용하지만, 실제로는 다른 파일일 수 있습니다.
    input_common_file = 'data/spot_metadata.json'  # overview, title, cat codes 등 기본 정보
    input_info_file = 'data/spot_metadata.json'  # 예: kidsfacility, chkbabycarriage 등 (detailCommon)
    input_intro_file = 'data/spot_metadata.json'  # 예: firstmenu, parkingfood, usefee 등 (detailIntro)

    # 출력 파일 경로들
    faiss_index_output_file ="data/spot_index.faiss"
    faiss_id_map_output_file = "data/spot_id_map.json"

    # 영구적인 요약 캐시 파일
    PERSISTENT_SUMMARY_CACHE_FILE = "data/persistent_spot_summaries.json"

    # 실행별 고유 파일 (필요시 사용, 현재는 사용 안함)
    # output_paths_for_run_specific_files = get_unique_output_paths("spot_run_output")

    print(f"요약 캐시 파일로 '{PERSISTENT_SUMMARY_CACHE_FILE}'을 사용합니다.")

    # 파일 존재 여부 확인
    required_files = [input_common_file, input_info_file, input_intro_file]
    missing_files = [f for f in required_files if not os.path.exists(f)]
    if missing_files:
        print(f"❌ 오류: 다음 입력 파일들을 찾을 수 없습니다: {', '.join(missing_files)}")
        print("스크립트를 종료합니다.")
        exit()

    # 출력 디렉토리 생성
    os.makedirs("data", exist_ok=True)

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

    print("\nFAISS 인덱싱을 위한 텍스트(요약본)를 준비합니다...")
    sorted_content_ids = sorted(all_summaries_map.keys())
    texts_for_embedding: List[str] = []
    ordered_content_ids_for_faiss_map: List[str] = []

    for cid in sorted_content_ids:
        summary = all_summaries_map.get(cid, "")

        if summary and summary.strip():  # 비어있지 않은 유효한 요약만 사용
            texts_for_embedding.append(summary)
            ordered_content_ids_for_faiss_map.append(cid)
        else:
            print(f"  Content ID '{cid}'의 요약이 비어있거나 없어 FAISS 인덱싱에서 제외됩니다.")

    if not texts_for_embedding:
        print("임베딩할 요약 텍스트가 없습니다. FAISS 인덱싱을 중단합니다.")
        exit()

    print(f"  총 {len(texts_for_embedding)}개의 유효한 요약에 대해 임베딩을 생성합니다...")

    embeddings = model.encode(texts_for_embedding, convert_to_numpy=True, show_progress_bar=True)
    print("임베딩 생성 완료.")

    if embeddings.ndim == 1 and embeddings.shape[0] > 0:  # 단일 임베딩이면서 비어있지 않은 경우
        embeddings = np.expand_dims(embeddings, axis=0)

    if embeddings.shape[0] == 0:  # 임베딩 결과가 없는 경우
        print("생성된 임베딩이 없습니다. FAISS 인덱스를 만들 수 없습니다.")
        exit()

    # L2 정규화 (유사도 검색 성능 향상에 도움)
    faiss.normalize_L2(embeddings)
    print("임베딩 L2 정규화 완료.")

    dimension = embeddings.shape[1]
    print(f"FAISS HNSW 인덱스를 생성합니다 (차원: {dimension})...")

    # HNSW 인덱스 생성 (M은 그래프에서 각 노드가 연결할 이웃 개수, 높을수록 정확도와 메모리 증가)
    # M의 일반적인 값: 16, 32, 48, 64. 데이터셋 크기와 검색 속도/정확도 요구사항에 따라 조절.
    M = 64
    index = faiss.IndexHNSWFlat(dimension, M, faiss.METRIC_INNER_PRODUCT)  # 정규화된 벡터에는 내적 사용

    # efConstruction: 인덱스 구축 시 탐색 그래프의 깊이/품질 (높을수록 구축 시간 증가, 검색 품질 향상 가능성)
    # 일반적인 값: M의 2배 ~ 4배, 또는 100~500 범위. 여기서는 기본값 또는 약간 높게 설정.
    index.hnsw.efConstruction = 500 # 기본값은 40. 필요시 조정.

    # efSearch: 검색 시 탐색 그래프의 깊이/품질 (높을수록 검색 시간 증가, 정확도 향상)
    # 일반적인 값: M보다 크거나 같게, 보통 64~256 범위. 여기서 efConstruction 값과 유사하게 설정 가능.
    index.hnsw.efSearch = 256  # 추천: 32~256 사이에서 튜닝
    print(f"  HNSW 파라미터: M={M}, efSearch={index.hnsw.efSearch}, efConstruction={index.hnsw.efConstruction} (기본값 또는 설정값)")

    index.add(embeddings)
    print("FAISS HNSW 인덱스에 임베딩 추가 완료.")
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
'''