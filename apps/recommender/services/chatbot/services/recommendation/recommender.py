from ...utils.embedding import model, faiss_index
from asgiref.sync import sync_to_async
from .score import core_item_score
from django.conf import settings
import json
import os

DATA_DIR = os.path.join(settings.BASE_DIR, 'apps', 'recommender', 'services', 'chatbot', 'data')

# 요약 정보만 로드 (index용)
with open(os.path.join(DATA_DIR, "persistent_spot_summaries.json"), "r", encoding="utf-8") as f:
    summaries = json.load(f)

# 메타데이터 로드 (점수 계산용)
with open(os.path.join(DATA_DIR, "spot_metadata.json"), "r", encoding="utf-8") as f:
    metadata = json.load(f)

@sync_to_async
def get_recommendations(query, user_profile, intent=None, keywords=None, top_n=5):
    """
    intent 및 쿼리에 따라 관광지를 추천합니다.
    조용한 장소 추천 요청(recommend_quiet)이면, 혼잡도(congestion_ratio) 기반 추천 수행
    그렇지 않으면 FAISS + 유사도 기반 추천 수행
    """
    scored_results = []

    if intent == "recommend_quiet":
        # 혼잡도(congestion_ratio)가 낮은 순으로 정렬
        items = sorted(
            metadata.items(),
            key=lambda x: x[1].get("congestion_ratio", 1.0)
        )
        for contentid, item in items:
            if item["title"] in user_profile.get("visited", []):
                continue
            score = 1.0 - item.get("congestion_ratio", 1.0)  # 낮을수록 점수 높게
            scored_results.append((item, score))
            if len(scored_results) >= top_n * 3:
                break

    else:
        # 일반 쿼리: FAISS 기반 유사도 추천
        query_vec = model.encode([query])
        D, I = faiss_index.search(query_vec, top_n * 5)

        content_ids = list(summaries.keys())
        for idx in I[0]:
            contentid = content_ids[idx]
            item = metadata.get(contentid)
            if not item:
                continue
            score = core_item_score(item, user_profile, intent=intent, keywords=keywords)
            if score is not None:
                scored_results.append((item, score))

    # 점수순 정렬 후 top_n개 추출
    ranked = sorted(scored_results, key=lambda x: -x[1])[:top_n]
    return [item for item, score in ranked]