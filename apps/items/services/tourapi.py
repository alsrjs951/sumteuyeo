from openai import OpenAI
from typing import Optional, Dict, List, Any
from django.conf import settings
from apps.items.models import ContentSummarize
import requests
import time
import logging
import json

logger = logging.getLogger(__name__)


client = OpenAI(api_key=settings.OPENAI_API_KEY)

def parse_binary_flag(value, yes_text, no_text):
    if value == "1":
        return yes_text
    elif value == "0":
        return no_text
    return ""

#intro, info에 있는 추천에 필요한 속성들 combine 하기전 재료 준비
def generate_intro_text(intro: Dict[str, Any], info: Dict[str, Any], cat_code: str, cat_dict: Dict[str, str] = None) -> str:
    parts = []

    if not intro:
        return ""

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

    if cat_dict and cat_code:
        cat_desc = cat_dict.get(str(cat_code), "")
        if cat_desc:
            parts.append(f"{cat_desc} 카테고리에 속한 장소입니다.")

    return " ".join(parts)

def get_summarize_content(content_id: int, content_type_id: int) -> Optional[str]:
    """
    content_id에 대한 요약문 반환 함수
    1) DB에 요약문이 있으면 반환
    2) 없으면 TourAPI 호출 후 GPT 요약 생성, DB 저장 후 반환
    3) TourAPI 데이터 없으면 None 반환
    """
    try:
        # 1. DB에서 요약문 조회
        obj = ContentSummarize.objects.get(contentid=content_id)
        return obj.summarize_text

    except ContentSummarize.DoesNotExist:
        # 2. DB에 없으면 TourAPI 호출
        common = get_tourapi_detail('detailCommon2', content_id, settings.TOUR_API_KEY, content_type_id)
        info = get_tourapi_detail('detailInfo2', content_id, settings.TOUR_API_KEY, content_type_id)
        intro = get_tourapi_detail('detailIntro2', content_id, settings.TOUR_API_KEY, content_type_id)

        # TourAPI 데이터가 모두 없으면 None 반환
        if not any([common, info, intro]):
            return None

        # cat_code는 예시로, 실제로는 common에서 받아오거나 별도 처리가 필요
        cat_code = common.get("lclsSystm3", "") if common else ""

        try:
            with open('cat_dict.json', 'r', encoding='utf-8') as f:
                cat_dict = json.load(f)
        except FileNotFoundError:
            logger.error("cat_dict.json 파일을 찾을 수 없습니다.")
            cat_dict = {}


        # 공통 정보
        title = common.get("title", "") if common else ""
        overview = common.get("overview", "") if common else ""

        # 소개 정보 생성
        intro_text = generate_intro_text(
            intro if intro else {},
            info if info else {},
            cat_code,
            cat_dict
        )

        # 최종 조합 텍스트 생성
        fields = []
        if title:
            fields.append(f"이곳은 '{title}'입니다.")
        if overview:
            fields.append(overview)
        if intro_text:
            fields.append(intro_text)

        combined_text = " ".join([f for f in fields if f]).strip()

        # GPT 요약 생성 (단일 요약엔 gpt_summarize 사용)
        summarize_content = gpt_summarize(combined_text)

        # 요약문이 생성되었으면 DB에 저장
        if summarize_content:
            ContentSummarize.objects.create(
                contentid=content_id,
                summarize_text=summarize_content
            )
            return summarize_content

        # 요약문 생성 실패 시 None 반환
        return None


def gpt_summarize(text: str) -> str:
    """
    여러 항목의 텍스트를 GPT로 요약하고, 결과를 DB에 저장하는 함수.
    반환값은 {id: summary} 딕셔너리 (실패 시 빈 딕셔너리)
    """
    if not text:
        return ""

    # 프롬프트
    system_prompt = "당신은 ‘관광지 요약 엔진’입니다. 장소 설명을 입력받아 해당 장소에 대한 요약문을 반환합니다."
    user_prompt = f"""
아래 장소 설명 텍스트를 기반으로
각 장소에 대해 다음 기준에 따라 **30~40단어 이내의 장소 요약 문장**을 생성하세요:
1. 장소 종류, 음식 종류 또는 서비스 카테고리를 **명확히 명시**할 것.
2. **정체성(분위기/특색)**, **위치/접근성**, **대표 콘텐츠(메뉴/전시/체험)**, **대상층(연인/가족/반려동물 등)** 등을 고루 표현하고 **추천 방문 시기, 한적도** 등을 자연스럽고 감성적인 **대상 맞춤 추천 문장**으로 표현할 것.
3. 불필요한 중복은 제거하되, 검색 가능성을 위해 **핵심 키워드**는 포함할 것.
4. 마치 관광지 추천 플랫폼에서 추천 문구로 쓰이는 자연스러운 어조로 작성할 것.
예) "제주 서쪽 송악산 인근의 송악산둘레길은 봄~가을 걷기 좋은 화산 트레일로, 연인, 가족과 반려동물 동반 산책객에게 적합한 한적한 코스입니다"

텍스트: {text}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
            max_tokens=150 + 500
        )
        summary = response.choices[0].message.content if hasattr(response.choices[0].message, 'content') else \
            response.choices[0]['message']['content']
        return summary.strip()
    except Exception as e:
        return ""


# TourAPI 의 detail 종류의 api_type 일 때만 이 함수를 사용할 것. (공통/소개/반복/이미지)
def get_tourapi_detail(
    api_type: str,
    contentid: int,
    service_key: str,
    contenttypeid: int = None,
    max_retries: int = 1
) -> Optional[Dict]:
    """
    TourAPI의 detail 종류 API 호출.
    - 정상적으로 데이터를 받으면 단일 dict 반환
    - 데이터가 없거나 오류 발생 시 None 반환
    """
    base_url = f"http://apis.data.go.kr/B551011/KorService2/{api_type}"
    params = {
        'serviceKey': service_key,
        'MobileOS': 'ETC',
        'MobileApp': 'sumteuyeo',
        'contentId': contentid,
        '_type': 'json'
    }

    if contenttypeid:
        if api_type not in ('detailCommon2', 'detailImage2'):
            params['contentTypeId'] = contenttypeid

    for retry in range(max_retries):
        try:
            response = requests.get(base_url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            # 응답 구조 파싱
            response_body = data.get('response', {})
            if not isinstance(response_body, dict):
                print(f"[TourAPI] Invalid response type: {type(response_body)}")
                return None

            body = response_body.get('body', {})
            if not isinstance(body, dict):
                print(f"[TourAPI] Invalid body type: {type(body)}")
                return None

            items = body.get('items')
            if not items:
                return None

            item = items.get('item')
            if isinstance(item, list):
                return item[0] if item else None
            elif isinstance(item, dict):
                return item
            else:
                print(f"[TourAPI] Unexpected 'item' type: {type(item)}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"[TourAPI][Attempt {retry+1}/{max_retries}] API call failed: {e}")
            if retry == max_retries - 1:
                return None
            time.sleep(0.5 * (retry + 1))
        except (ValueError, KeyError) as e:
            print(f"[TourAPI] Data validation error: {e}")
            return None

    return None

def get_nearby_content_ids(user_lat: float, user_lng: float, radius_km: int = 20) -> List[int]:
    """
    TourAPI locationBasedList1을 호출하여 최대 5만개까지 주변 콘텐츠 ID 리스트 반환
    """
    base_url = "http://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    service_key = settings.TOUR_API_KEY
    radius_meters = radius_km * 1000
    all_content_ids = []
    num_of_rows = 50000
    max_pages = 1

    for page_no in range(1, max_pages + 1):
        params = {
            'serviceKey': service_key,
            'MobileOS': 'ETC',
            'MobileApp': 'sumteuyeo',
            '_type': 'json',
            'mapX': user_lng,
            'mapY': user_lat,
            'radius': radius_meters,
            'pageNo': page_no,
            'numOfRows': num_of_rows,
            'arrange': 'E'
        }
        try:
            response = requests.get(base_url, params=params, timeout=15)
            response.raise_for_status()
            data = response.json()
            items = data.get('response', {}).get('body', {}).get('items', {})
            if not items:
                break
            item_list = items.get('item', [])
            if isinstance(item_list, dict):
                item_list = [item_list]
            page_content_ids = [
                int(item['contentid']) for item in item_list if item.get('contentid')
            ]
            if not page_content_ids:
                break
            all_content_ids.extend(page_content_ids)
            logger.info(f"페이지 {page_no}: {len(page_content_ids)}개 콘텐츠 수집, 누적 {len(all_content_ids)}개")
            # 마지막 페이지인지 확인
            total_count = data.get('response', {}).get('body', {}).get('totalCount', 0)
            if page_no * num_of_rows >= total_count:
                break
            time.sleep(0.2)  # 호출 제한 대응
        except Exception as e:
            logger.error(f"페이지 {page_no} 처리 실패: {str(e)}")
            break

    # 중복 제거
    unique_content_ids = list(set(all_content_ids))
    return unique_content_ids
