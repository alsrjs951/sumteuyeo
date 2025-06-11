from ...utils.embedding import model, faiss_index, normalize_query
from asgiref.sync import sync_to_async
from .score import core_item_score
from django.conf import settings
from ...constants import cat_dict
import json
import os
from .cross_encoder_trainer import KCrossEncoderReranker

#재랭킹 모델 로딩
reranker = KCrossEncoderReranker("C:/django/sumteuyeo/apps/recommender/services/chatbot/services/recommendation/reranker_model")

# 데이터 경로 설정
DATA_DIR = os.path.join(settings.BASE_DIR, 'apps', 'recommender', 'services', 'chatbot', 'data')
SPOT_METADATA_PATH = os.path.join(DATA_DIR, "spot_metadata.json")  # ✅ 추가

def load_metadata_as_dict(path):
    """리스트 형태의 spot_metadata를 contentid 기준으로 딕셔너리 변환"""
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return {str(item["contentid"]): item for item in raw if "contentid" in item}  # ✅ contentid를 문자열로 변환

# 요약 정보 로드
with open(os.path.join(DATA_DIR, "persistent_spot_summaries.json"), "r", encoding="utf-8") as f:
    summaries = json.load(f)

# 메타데이터를 dict로 변환해 로드
metadata = load_metadata_as_dict(SPOT_METADATA_PATH)  # ✅ 수정된 부분


@sync_to_async
def get_recommendations(query, user_profile, intent=None, keywords=None, top_n=5):
    """
    intent 및 쿼리에 따라 관광지를 추천합니다.
    Cross-Encoder 재랭킹이 적용됩니다.
    """
    scored_results = []
    seen_content_ids = set()  # 중복 방지용 집합

    if intent == "recommend_quiet":
        items = sorted(
            metadata.items(),
            key=lambda x: x[1].get("congestion_ratio", 1.0)
        )
        for contentid, item in items:
            if item["title"] in user_profile.get("visited", []):
                continue
            if contentid in seen_content_ids:
                continue
            score = 1.0 - item.get("congestion_ratio", 1.0)
            scored_results.append((item, score))
            seen_content_ids.add(contentid)
            if len(scored_results) >= top_n * 5:
                break
        # 조용한 장소 추천은 Cross-Encoder 재랭킹 적용 (선택 사항)
        candidates = [item for item, score in scored_results]
        if candidates:  # 후보군이 있을 때만 재랭킹
            ranked_items = reranker.rerank(query, candidates, top_n)
            return ranked_items
        else:
            return []

    else:
        query_vec = model.encode([normalize_query(query)])
        D, I = faiss_index.search(query_vec, top_n * 20)

        content_ids = list(summaries.keys())
        for idx in I[0]:
            contentid = content_ids[idx]
            if contentid in seen_content_ids:
                continue
            item = metadata.get(contentid)
            if not item:
                continue
            score = core_item_score(item, user_profile, intent=intent, keywords=keywords, cat_dict=cat_dict)
            if score is not None:
                scored_results.append((item, score))
                seen_content_ids.add(contentid)
        # 점수순 정렬 후 상위 (top_n * m)개만 Cross-Encoder 재랭킹 대상으로 추출
        ranked = sorted(scored_results, key=lambda x: -x[1])[:top_n * 20]
        candidates = [item for item, score in ranked]
        # Cross-Encoder 재랭킹
        ranked_items = reranker.rerank(query, candidates, top_n)
        print(ranked_items)
        return ranked_items


def get_places_summary_by_contentids(contentids, spot_data_dict):
    places_summary_list = []
    for contentid in contentids:
        item = spot_data_dict.get(str(contentid))
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
            'lclsSystm3': item.get('lclsSystm3', ''),
            'contenttypeid': item.get('contenttypeid')
        })
    return places_summary_list
