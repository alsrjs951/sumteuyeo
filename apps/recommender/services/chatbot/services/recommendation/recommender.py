from ...utils.embedding import model, faiss_index, normalize_query
from asgiref.sync import sync_to_async
from .score import core_item_score
from django.conf import settings
from ...constants import cat_dict, INTENT_TO_CATEGORY_MAP
import json
import os
from .cross_encoder_trainer import KCrossEncoderReranker
from ...utils.ner import extract_locations_from_query  # 👈 NER 기반 지역 추출 함수
from django.http import JsonResponse

# --- 데이터 및 모델 로딩 ---
DATA_DIR = os.path.join(settings.BASE_DIR, 'apps', 'recommender', 'services', 'chatbot', 'data')
SPOT_METADATA_PATH = os.path.join(DATA_DIR, "spot_metadata.json")
SUMMARIES_PATH = os.path.join(DATA_DIR, "persistent_spot_summaries.json")
model_id = "udol/sumteuyeo-cross"

def load_metadata_as_dict(path):
    with open(path, "r", encoding="utf-8") as f:
        raw_list = json.load(f)
    return {str(item["contentid"]): item for item in raw_list if "contentid" in item}

with open(SUMMARIES_PATH, "r", encoding="utf-8") as f:
    summaries = json.load(f)
metadata = load_metadata_as_dict(SPOT_METADATA_PATH)

reranker = KCrossEncoderReranker(
    model_path=model_id,
    summaries=summaries
)

@sync_to_async
def get_recommendations(query, user_profile, intent=None, keywords=None, top_n=5):
    """
    사용자 쿼리와 의도에 따라 관광지를 추천합니다.
    NER 기반 지역 필터링 + 카테고리 + 점수 기반 재랭킹 구조.
    """
    scored_results = []
    seen_content_ids = set()

    # Case 1: '한적한 곳' 추천
    if intent == "recommend_quiet":
        items = sorted(metadata.items(), key=lambda x: x[1].get("congestion_ratio", 1.0))
        for contentid, item in items:
            if item.get("title") in user_profile.get("visited", []):
                continue
            if contentid in seen_content_ids:
                continue
            score = 1.0 - item.get("congestion_ratio", 1.0)
            scored_results.append((item, score))
            seen_content_ids.add(contentid)
            if len(scored_results) >= top_n * 5:
                break
        candidates = [item for item, score in scored_results]
        return reranker.rerank(query, candidates, top_n) if candidates else []

    # Case 2: 일반 추천
    else:
        # 1. NER 기반 지역명 추출 (사전 정의된 함수 사용)
        extracted_locations = extract_locations_from_query(query)  # ['제주', '경주'] 등
        extracted_locations_set = set(extracted_locations) if extracted_locations else set()

        # 2. 의도 기반 필수 카테고리 확인
        required_category = INTENT_TO_CATEGORY_MAP.get(intent)

        # 3. FAISS 전체에서 1차 후보군 검색
        query_vec = model.encode([normalize_query(query)])
        D, I = faiss_index.search(query_vec, top_n * 100)
        faiss_candidate_ids = [list(summaries.keys())[idx] for idx in I[0]]

        # 4. 지역명 기반 후처리 필터링 + 카테고리 체크 + 점수 계산
        for contentid in faiss_candidate_ids:
            if contentid in seen_content_ids:
                continue

            item = metadata.get(contentid)
            if not item:
                continue

            # 지역명 필터링
            if extracted_locations_set:
                item_addr = item.get("addr1", "") + item.get("addr2", "")
                if not any(loc in item_addr for loc in extracted_locations_set):
                    continue

            # 카테고리 필터링
            if required_category and str(item.get("contenttypeid")) != required_category:
                continue

            # 점수 계산
            score = core_item_score(item, user_profile, intent=intent, keywords=keywords, cat_dict=cat_dict)
            if score is not None:
                scored_results.append((item, score))
                seen_content_ids.add(contentid)

        if not scored_results:
            return []

        # 5. 점수 상위 항목 rerank
        ranked_by_score = sorted(scored_results, key=lambda x: -x[1])[:top_n * 100]
        candidates = [item for item, score in ranked_by_score]
        return reranker.rerank(query, candidates, top_n)

def get_places_summary_by_contentids(contentids, spot_data_dict):
    places_summary_list = []
    for content_id in contentids:
        item = spot_data_dict.get(str(content_id))
        if not item:
            continue
        addr1 = item.get('addr1', '')
        addr2 = item.get('addr2', '')
        address_parts = []
        if addr1 and addr1.strip():
            address_parts.append(addr1.strip())
        if addr2 and addr2.strip():
            address_parts.append(addr2.strip())
        full_address = " ".join(address_parts)

        places_summary_list.append({
            'contentid': item.get('contentid'),
            'title': item.get('title', '이름 없음'),
            'addr': full_address,
            'tel': item.get('tel', ''),
            'firstimage': item.get('firstimage', ''),
            'contenttypeid': item.get('contenttypeid')
        })
    return places_summary_list
