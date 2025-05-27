from openai import OpenAI
from typing import Optional, Dict
from django.conf import settings
from items.models import ContentSummarize
import requests
import time

client = OpenAI(api_key=settings.OPENAI_API_KEY)

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

        fields = []

        # 공통 정보
        if common:
            fields.append(common.get("title", ""))
            fields.append(common.get("overview", ""))

        # 상세 정보
        if info:
            infoname = info.get("infoname", "")
            infotext = info.get("infotext", "")
            if infoname or infotext:
                fields.append(f"{infoname}: {infotext}")

        # 소개 정보
        if intro:
            for key in ["heritage1", "heritage2", "heritage3", "firstmenu", "treatmenu", "kidsfacility"]:
                val = intro.get(key)
                if val:
                    fields.append(f"{key}: {val}")

        combined_text = " / ".join([f for f in fields if f])

        # GPT 요약 생성
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
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "당신은 ‘관광지 종합 요약 엔진’입니다."},
                {"role": "user", "content": f"""
 주어진 필드에서 핵심 정보를 추출하고, 분위기, 방문 시기, 타깃, 액티비티, 혼잡도 등 숨은 매력도 보완해서 정체성, 매력, 즐길 거리, 대상층이 고루 드러나도록 20~30단어 이내 한 문장으로 요약
텍스트: {text}
"""}
            ],
            temperature=0.5,
            max_tokens=300
        )
        summary = response.choices[0].message.content if hasattr(response.choices[0].message, 'content') else \
        response.choices[0]['message']['content']
        summary = summary.strip()
        return summary
    except Exception as e:
        print(f"GPT 호출 오류: {e}")
        return ""


# TourAPI 의 detail 종류의 api_type 일 때만 이 함수를 사용할 것. (공통/소개/반복/이미지)
def get_tourapi_detail(
    api_type: str,
    contentid: int,
    service_key: str,
    contenttypeid: int = None,
    max_retries: int = 3
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
