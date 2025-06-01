from ...utils.embedding import model, faiss_index
from asgiref.sync import sync_to_async
from .score import core_item_score
from django.conf import settings
import json
import os

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
    """
    scored_results = []
    seen_content_ids = set()  # ✅ 중복 방지용 집합

    if intent == "recommend_quiet":
        items = sorted(
            metadata.items(),
            key=lambda x: x[1].get("congestion_ratio", 1.0)
        )
        for contentid, item in items:
            if item["title"] in user_profile.get("visited", []):
                continue
            if contentid in seen_content_ids:  # ✅ 중복 방지
                continue
            score = 1.0 - item.get("congestion_ratio", 1.0)
            scored_results.append((item, score))
            seen_content_ids.add(contentid)  # ✅ contentid 등록
            if len(scored_results) >= top_n * 3:
                break

    else:
        query_vec = model.encode([query])
        D, I = faiss_index.search(query_vec, top_n * 5)

        content_ids = list(summaries.keys())
        for idx in I[0]:
            contentid = content_ids[idx]
            if contentid in seen_content_ids:  # ✅ 중복 방지
                continue
            item = metadata.get(contentid)
            if not item:
                continue
            score = core_item_score(item, user_profile, intent=intent, keywords=keywords)
            if score is not None:
                scored_results.append((item, score))
                seen_content_ids.add(contentid)  # ✅ 등록

    # 점수순 정렬 후 top_n개 추출
    ranked = sorted(scored_results, key=lambda x: -x[1])[:top_n]
    return [item for item, score in ranked]
