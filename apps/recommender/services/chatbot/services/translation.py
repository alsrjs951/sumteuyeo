import httpx
import json


# googletrans 라이브러리는 더 이상 사용하지 않습니다.
# from googletrans import Translator
# from asgiref.sync import sync_to_async

# translator = Translator() # 제거

# ⭐️ [변경점 1] 네이티브 비동기 함수로 재작성. @sync_to_async 제거.
async def translate_text(text: str, dest: str) -> str:
    """
    httpx를 사용하여 Google 번역 API를 직접 호출하는 비동기 번역 함수입니다.

    Args:
        text (str): 번역할 텍스트.
        dest (str): 목표 언어 코드 (예: 'ko', 'en').

    Returns:
        str: 번역된 텍스트. 오류 발생 시 원본 텍스트 반환.
    """
    if not text:
        return ""

    # Google 번역 API 엔드포인트
    url = "https://translate.googleapis.com/translate_a/single"

    # API가 요구하는 파라미터 설정
    params = {
        "client": "gtx",
        "sl": "auto",  # 소스 언어 자동 감지
        "tl": dest,  # 목표 언어
        "dt": "t",  # 번역된 텍스트만 요청
        "q": text,
    }

    try:
        # 비동기 HTTP 클라이언트를 사용하여 API 요청
        async with httpx.AsyncClient() as client:
            # ⭐️ 바로 이 부분이 핵심입니다. 네트워크 요청을 'await'로 기다립니다.
            response = await client.get(url, params=params)
            response.raise_for_status()  # 200 OK가 아니면 오류 발생

        # Google API의 응답은 복잡한 리스트 형태이므로, 번역된 텍스트만 추출합니다.
        result_list = response.json()
        translated_text = "".join([item[0] for item in result_list[0]])
        return translated_text

    except (httpx.RequestError, json.JSONDecodeError, IndexError) as e:
        print(f"💥 번역 중 오류 발생: {e}")
        # 오류 발생 시, 안전하게 원본 텍스트를 반환
        return text


# ⭐️ [변경점 2] 기존 함수들을 새로운 비동기 함수를 호출하도록 변경
async def translate_to_korean(text: str) -> str:
    """텍스트를 한국어로 비동기 번역합니다."""
    return await translate_text(text, dest="ko")


async def translate_to_original(text: str, dest: str) -> str:
    """텍스트를 지정된 언어로 비동기 번역합니다."""
    return await translate_text(text, dest=dest)
