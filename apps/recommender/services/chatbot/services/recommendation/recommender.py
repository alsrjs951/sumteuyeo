import json
import os
import geopy.distance  # 거리 계산을 위한 라이브러리 (pip install geopy)
import re
from asgiref.sync import sync_to_async
from .score import core_item_score, calculate_hidden_trendy_score
from django.conf import settings
from ...constants import cat_dict, INTENT_TO_CATEGORY_MAP, Intent
from ...utils.filtering import INTENT_PATTERNS
from .cross_reranking import KCrossEncoderReranker
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


metadata = load_metadata_as_dict(SPOT_METADATA_PATH)

reranker = KCrossEncoderReranker(
    model_path=model_id,
    summaries=summaries
)

@sync_to_async
def get_recommendations(user_input, user_profile, intent=None, keywords=None, extracted_locations=None,
                        user_location=None, top_n=5):
    # 1순위: '주변 추천' 로직
    if intent.value == "recommend_nearby" and user_location:
        print(f"📍 '주변 추천' 로직 실행... 사용자 위치: {user_location}")

        # ⭐️ [핵심 수정] 키워드를 바탕으로 목표 카테고리를 동적으로 추론
        target_category_id = None
        # 사용자의 키워드 (예: '햄버거집')가 어떤 의도 패턴에 속하는지 확인
        for keyword in keywords:
            for intent_enum, patterns in INTENT_PATTERNS.items():
                # '음식' 관련 의도에 '햄버거집' 키워드가 매칭되는지 검사
                if intent_enum.value.startswith("recommend_") and intent_enum != Intent.RECOMMEND_NEARBY:
                    for pattern in patterns:
                        if re.search(pattern, keyword):
                            # 매칭되는 의도를 찾으면, 해당 의도의 카테고리 ID를 가져옴
                            target_category_id = INTENT_TO_CATEGORY_MAP.get(intent_enum.value)
                            break
            if target_category_id:
                break

        # 만약 '근처 가볼만한 곳'처럼 키워드가 없다면, 관광지(12)를 기본값으로 설정
        if not target_category_id:
            target_category_id = '12'  # 기본값: 관광지

        print(f"  - 주변 탐색 타겟 카테고리: {target_category_id}")

        nearby_places = []
        user_point = (user_location['lat'], user_location['lng'])
        search_radius_km = 3

        for contentid, item in metadata.items():
            # 카테고리 필터링
            if str(item.get("contenttypeid")) != target_category_id:
                continue

            # 거리 계산 및 반경 필터링
            if item.get("mapy") and item.get("mapx"):
                item_point = (float(item["mapy"]), float(item["mapx"]))
                distance = geopy.distance.geodesic(user_point, item_point).km

                if distance <= search_radius_km:
                    item_with_dist = item.copy()
                    item_with_dist['distance_km'] = round(distance, 2)
                    nearby_places.append(item_with_dist)

        sorted_places = sorted(nearby_places, key=lambda x: x['distance_km'])
        print(f"📍 총 {len(sorted_places)}개의 주변 장소 발견. 가까운 순서대로 {top_n}개 반환.")
        return sorted_places[:top_n]

    # ⭐️ [변경점 2] 기존 '한적한 곳' 로직을 'elif'로 변경
    elif intent.value == "recommend_quite":
        print("🤫 '숨은 트렌디 여행지' 추천 로직 실행...")
        # ... (기존 'recommend_quiet' 로직은 여기에 그대로 붙여넣으세요) ...
        scored_results = []
        for contentid, item in metadata.items():
            if item.get("title") in user_profile.get("visited", []): continue
            if extracted_locations:
                item_addr = item.get("addr1", "") + item.get("addr2", "")
                if not any(loc in item_addr for loc in extracted_locations): continue
            score = calculate_hidden_trendy_score(item, cat_dict)
            scored_results.append((item, score))
        ranked_by_score = sorted(scored_results, key=lambda x: -x[1])
        candidates = [item for item, score in ranked_by_score[:top_n * 10]]
        print(f"🤫 총 {len(candidates)}개의 '숨은 명소' 후보를 최종 리랭킹합니다.")
        return reranker.rerank(user_input, candidates, top_n) if candidates else []

    # ⭐️ [변경점 3] 기존 '일반 추천' 로직은 'else'로 처리 (변경 없음)
    else:
        # ... (기존 '선필터링, 후랭킹' 일반 추천 로직은 여기에 그대로 붙여넣으세요) ...
        extracted_locations_set = set(extracted_locations) if extracted_locations else set()
        required_category = INTENT_TO_CATEGORY_MAP.get(intent.value)
        print(f"✅ Recommender 시작 | 지역: {extracted_locations_set} | 카테고리: {required_category}")

        def _filter_first(loc_filter, cat_filter):
            # ... _filter_first 함수 내용 ...
            pre_filtered_items = []
            for contentid, item in metadata.items():
                if loc_filter:
                    item_addr = item.get("addr1", "") + item.get("addr2", "")
                    if not any(loc in item_addr for loc in loc_filter): continue
                if cat_filter:
                    if str(item.get("contenttypeid")) != cat_filter: continue
                pre_filtered_items.append(item)
            return pre_filtered_items

        candidates = _filter_first(extracted_locations_set, required_category)
        print(f"1️⃣  [1차 필터링] 후 후보 수: {len(candidates)}개")
        if not candidates and extracted_locations_set:
            candidates = _filter_first(extracted_locations_set, None)
            print(f"2️⃣  [1차 필터링-완화] 후 후보 수: {len(candidates)}개")
        if not candidates and required_category:
            candidates = _filter_first(None, required_category)
            print(f"3️⃣  [1차 필터링-완화] 후 후보 수: {len(candidates)}개")
        if not candidates: return []
        print(f"🏆 {len(candidates)}개 후보 대상, core_item_score로 2차 랭킹 시작...")
        scored_results = []
        for item in candidates:
            score = core_item_score(item, user_profile, intent=intent, keywords=keywords, cat_dict=cat_dict)
            scored_results.append((item, score))
        ranked_by_score = sorted(scored_results, key=lambda x: -x[1])
        final_candidates = [item for item, score in ranked_by_score]
        print(f"📊 [2차 랭킹] 완료. 상위 후보: '{final_candidates[0]['title']}' (점수: {ranked_by_score[0][1]:.4f})")
        print(f"🏅 상위 {min(len(final_candidates), top_n * 15)}개 후보를 Reranker로 최종 리랭킹합니다.")
        return reranker.rerank(user_input, final_candidates[:top_n * 15], top_n)


#거리 기반 추천 함수(유도질문에 사용)
@sync_to_async
def get_nearby_recommendations(anchor_content_ids: list, target_category_id: str, search_radius_km: int = 3,
                               top_n: int = 5):
    """
    주어진 기준 장소들 근처에서 특정 카테고리의 장소를 찾아 추천합니다.
    """
    print(f"--- 주변 추천 시작: 기준 ID({anchor_content_ids}), 타겟 카테고리({target_category_id}) ---")

    nearby_places = []

    # 1. 기준 장소들의 평균 좌표 계산
    anchor_coords = []
    for cid in anchor_content_ids:
        item = metadata.get(cid)
        if item and item.get("mapy") and item.get("mapx"):
            anchor_coords.append((float(item["mapy"]), float(item["mapx"])))

    if not anchor_coords:
        return []

    # 위도, 경도의 평균을 내어 중심점을 찾음
    center_lat = sum(coord[0] for coord in anchor_coords) / len(anchor_coords)
    center_lon = sum(coord[1] for coord in anchor_coords) / len(anchor_coords)
    center_point = (center_lat, center_lon)
    print(f"  - 검색 중심 좌표: {center_point}")

    # 2. 전체 metadata를 순회하며 조건에 맞는 장소 찾기
    for contentid, item in metadata.items():
        # 타겟 카테고리와 일치하는지 확인
        if str(item.get("contenttypeid")) == target_category_id:
            # 좌표 정보가 있는지 확인
            if item.get("mapy") and item.get("mapx"):
                item_point = (float(item["mapy"]), float(item["mapx"]))
                # 중심점과의 거리 계산
                distance = geopy.distance.geodesic(center_point, item_point).km

                # 검색 반경 내에 있다면 후보에 추가
                if distance <= search_radius_km:
                    item_with_dist = item.copy()  # 원본 수정을 피하기 위해 복사
                    item_with_dist['distance_km'] = distance
                    nearby_places.append(item_with_dist)

    # 3. 가까운 순서대로 정렬하여 상위 N개 반환
    sorted_places = sorted(nearby_places, key=lambda x: x['distance_km'])
    print(f"  - {len(sorted_places)}개의 주변 장소 발견. 가까운 순서대로 {top_n}개 반환.")

    return sorted_places[:top_n]

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
