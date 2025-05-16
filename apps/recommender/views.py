import json
import requests  # 외부 API 호출을 위한 라이브러리
import re  # 홈페이지 URL 파싱을 위한 정규표현식 라이브러리
import certifi  # SSL 인증서 경로를 명시적으로 사용하기 위해 추가

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_GET  # require_GET 추가
from django.shortcuts import render
from django.conf import settings


# --- Helper Function: 주변 관광지 목록 가져오기 (Lazy Loading 적용) ---
def get_nearby_places_list(latitude, longitude, api_key):  # 함수 이름 변경 (get_nearby_places -> get_nearby_places_list)
    """
    주어진 위도, 경도를 기반으로 TourAPI(locationBasedList1)를 호출하여
    주변 관광지 기본 정보 리스트(contentid 포함)를 반환합니다.
    상세 정보(개요, 홈페이지)는 포함하지 않습니다.
    requests.get 호출 시 verify 경로를 명시합니다.

    Args:
        latitude (float): 사용자 위도
        longitude (float): 사용자 경도
        api_key (str): TourAPI 인증키

    Returns:
        tuple: (places_list, error_message)
               성공 시 (list, None), 실패 시 ([], str) 형태
    """
    places_summary_list = []  # 반환할 리스트 이름 변경
    error_message = None

    try:
        ca_bundle_path = certifi.where()
    except Exception as e:
        print(f"Error getting certifi path: {e}")
        return [], "certifi CA 번들 경로를 찾는 중 오류가 발생했습니다."

    location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    location_params = {
        'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'mapX': longitude, 'mapY': latitude, 'radius': 20000,  # 반경 20km
        'listYN': 'Y', 'arrange': 'E',  # 거리순 정렬
        'contentTypeId': 12,  # 관광지 타입
        'numOfRows': 20,  # 가져올 아이템 수
        '_type': 'json'
    }

    response_loc = None
    try:
        print("Attempting to call locationBasedList1 API (with explicit verify path)...")
        response_loc = requests.get(
            location_api_url,
            params=location_params,
            timeout=10,
            verify=ca_bundle_path
        )
        response_loc.raise_for_status()
        api_data_loc = response_loc.json()
        print("locationBasedList1 API call successful.")

        if api_data_loc['response']['header']['resultCode'] != '0000':
            error_message = api_data_loc['response']['header'].get('resultMsg', '위치 기반 API 오류')
            print(f"TourAPI Error (locationBasedList1): {error_message}")
            return [], f'주변 관광지 목록 API 오류: {error_message}'

        items_data = api_data_loc['response']['body'].get('items', {})
        items = items_data.get('item', [])

        if items:
            for item in items:
                places_summary_list.append({
                    'contentid': item.get('contentid'),  # 프론트엔드에서 상세 정보 요청 시 사용
                    'title': item.get('title', '이름 없음'),
                    'addr1': item.get('addr1', ''),  # 주소
                    'firstimage': item.get('firstimage', ''),  # 대표 이미지
                    # 필요하다면 locationBasedList1에서 제공하는 다른 기본 정보 추가 가능
                    # 예: 'mapx': item.get('mapx'), 'mapy': item.get('mapy')
                })

        return places_summary_list, None

    except requests.exceptions.SSLError as e:
        error_message = 'SSL 인증서 검증 오류가 발생했습니다. (locationBasedList1)'
        print(f"!!! SSLError occurred (locationBasedList1): {e}")
        return [], error_message
    except requests.exceptions.Timeout:
        error_message = '주변 관광 정보 요청 시간이 초과되었습니다. (locationBasedList1)'
        print(f"API 요청 시간 초과 (locationBasedList1)")
        return [], error_message
    except requests.exceptions.RequestException as e:
        error_message = '주변 관광 정보를 가져오는 중 네트워크 오류가 발생했습니다. (locationBasedList1)'
        print(f"API 요청 오류 (locationBasedList1): {e}")
        if response_loc is not None:
            print(f"Response Status Code was: {response_loc.status_code}")
        return [], error_message
    except json.JSONDecodeError:
        error_message = '주변 관광 정보 API 응답 형식이 잘못되었습니다. (locationBasedList1)'
        print(f"JSON Decode Error (locationBasedList1)")
        if response_loc is not None:
            print(f"Received non-JSON response (locationBasedList1): {response_loc.text[:200]}")
        return [], error_message
    except Exception as e:
        error_message = '주변 관광 정보를 처리하는 중 알 수 없는 오류가 발생했습니다.'
        print(f"처리 중 오류 (locationBasedList1): {e}")
        return [], error_message


# --- 새로운 뷰 함수: 특정 관광지의 상세 정보 가져오기 ---
@require_GET  # GET 요청으로 상세 정보 조회
def get_place_detail_view(request, content_id):
    """
    주어진 content_id에 해당하는 관광지의 상세 정보(개요, 홈페이지)를 반환합니다.
    """
    try:
        TOUR_API_KEY = settings.TOUR_API_KEY
        if not TOUR_API_KEY:
            raise AttributeError("TOUR_API_KEY not found in settings.")
    except AttributeError as e:
        print(f"설정 오류: {e}")
        return JsonResponse({'status': 'error', 'message': 'API 키 설정에 문제가 발생했습니다.'}, status=500)

    try:
        ca_bundle_path = certifi.where()
    except Exception as e:
        print(f"Error getting certifi path: {e}")
        return JsonResponse({'status': 'error', 'message': 'certifi CA 번들 경로 오류'}, status=500)

    detail_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"
    detail_params = {
        'serviceKey': TOUR_API_KEY,
        'MobileOS': 'ETC',
        'MobileApp': 'Sumteuyeo',
        'contentId': content_id,
        '_type': 'json',
        'defaultYN': 'Y',  # 기본 정보 조회
        'firstImageYN': 'N',  # 대표 이미지는 이미 목록에서 받음 (필요시 Y)
        'areacodeYN': 'N',
        'catcodeYN': 'N',
        'addrinfoYN': 'N',  # 주소 정보는 이미 목록에서 받음 (필요시 Y)
        'mapinfoYN': 'N',  # 지도 정보는 이미 목록에서 받음 (필요시 Y)
        'overviewYN': 'Y'  # 개요 정보 조회
    }

    overview = ''
    homepage_url = ''
    response_detail = None
    response_detail_text = ''

    try:
        print(f"Attempting to call detailCommon1 API for contentId: {content_id} (with explicit verify path)...")
        response_detail = requests.get(
            detail_api_url,
            params=detail_params,
            timeout=5,
            verify=ca_bundle_path
        )
        response_detail_text = response_detail.text
        response_detail.raise_for_status()

        print(f"  ContentId {content_id} - Status Code: {response_detail.status_code}")
        # print(f"  ContentId {content_id} - Response Text Preview: {response_detail_text[:200]}")

        api_data_detail = response_detail.json()

        if api_data_detail['response']['header']['resultCode'] == '0000':
            detail_items_data = api_data_detail['response']['body'].get('items', {})
            detail_item = detail_items_data.get('item')
            # detailCommon1은 contentId로 조회시 항상 단일 아이템이거나, 없거나. 리스트로 올 경우 첫번째 아이템 선택
            if detail_item and isinstance(detail_item, list):
                detail_item = detail_item[0] if detail_item else None

            if detail_item and isinstance(detail_item, dict):
                overview = detail_item.get('overview', '')
                homepage_raw = detail_item.get('homepage', '')
                if homepage_raw:
                    # 정규표현식으로 a 태그의 href 값 추출
                    match = re.search(r'href=[\'"]?([^\'" >]+)', homepage_raw, re.IGNORECASE)
                    if match:
                        homepage_url = match.group(1)
                    # 간혹 URL만 텍스트로 오는 경우도 고려 (<a> 태그 없이)
                    elif 'http' in homepage_raw and '<' not in homepage_raw:
                        # 간단한 URL 패턴 검사 (더 정교하게 할 수도 있음)
                        url_match = re.search(r'(https?://[^\s<>"\'()]+)', homepage_raw)
                        if url_match:
                            homepage_url = url_match.group(1)
                        else:  # 그래도 못찾으면 원본 일부라도... (프론트에서 처리 필요할 수도)
                            homepage_url = homepage_raw.split()[0] if homepage_raw.split() else ''
                    else:
                        homepage_url = ''  # 파싱 실패 시 빈 값 또는 원본 텍스트 일부

                return JsonResponse({
                    'status': 'success',
                    'contentid': content_id,  # 요청했던 content_id 다시 보내주기
                    'overview': overview,
                    'homepage': homepage_url
                })
            else:
                # 아이템은 있으나 상세 정보가 없는 경우 (API 명세상 거의 없을듯하나 방어 코드)
                return JsonResponse({'status': 'error', 'message': '상세 정보를 찾을 수 없습니다.'}, status=404)

        else:
            detail_error = api_data_detail['response']['header'].get('resultMsg', '상세 정보 API 오류')
            print(
                f"TourAPI Warning (detailCommon1 for contentId {content_id}, resultCode {api_data_detail['response']['header']['resultCode']}): {detail_error}")
            return JsonResponse({'status': 'error', 'message': f'상세 정보 API 오류: {detail_error}'},
                                status=502)  # Bad Gateway (외부 API 문제)

    except requests.exceptions.SSLError as e:
        print(f"!!! SSLError occurred (detailCommon1 for contentId {content_id}): {e}")
        return JsonResponse({'status': 'error', 'message': 'SSL 인증서 검증 오류 (상세정보)'}, status=502)
    except requests.exceptions.Timeout:
        print(f"API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
        return JsonResponse({'status': 'error', 'message': '상세 정보 요청 시간 초과'}, status=504)  # Gateway Timeout
    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")
        if response_detail is not None:
            print(f"  Response Status Code was: {response_detail.status_code}")
        return JsonResponse({'status': 'error', 'message': '상세 정보 요청 중 네트워크 오류'}, status=502)
    except json.JSONDecodeError:
        print(f"JSON Decode Error (detailCommon1 for contentId {content_id})")
        if response_detail is not None:
            print(f"Received non-JSON response text: {response_detail_text}")
        return JsonResponse({'status': 'error', 'message': '상세 정보 API 응답 형식 오류'}, status=502)
    except Exception as e:
        print(f"Unexpected error processing detail for contentId {content_id}: {e}")
        return JsonResponse({'status': 'error', 'message': '상세 정보 처리 중 알 수 없는 서버 오류'}, status=500)


@ensure_csrf_cookie
def location_page_view(request):
    return render(request, 'core/main_page.html') # 탬플릿 경로 확인


@require_POST
def receive_location(request):  # 주변 관광지 "목록"을 요청하는 뷰
    try:
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'status': 'error', 'message': '필수 파라미터(latitude, longitude)가 누락되었습니다.'}, status=400)

        try:
            TOUR_API_KEY = settings.TOUR_API_KEY
            if not TOUR_API_KEY: raise AttributeError
        except AttributeError:
            error_msg = "settings.py에 TOUR_API_KEY가 정의되지 않았거나 비어있습니다."
            print(f"설정 오류: {error_msg}")
            return JsonResponse({'status': 'error', 'message': 'API 키 설정에 문제가 발생했습니다.'}, status=500)

        print("Calling get_nearby_places_list function...")
        # 수정된 함수 호출 (이름 변경 get_nearby_places -> get_nearby_places_list)
        places_summary_list, error_msg = get_nearby_places_list(latitude, longitude, TOUR_API_KEY)
        print(f"get_nearby_places_list returned. Error message: {error_msg}")

        if error_msg:
            print(f"Error detected in receive_location: {error_msg}")
            status_code = 500
            if "시간 초과" in error_msg:
                status_code = 504
            elif "네트워크 오류" in error_msg or "API 오류" in error_msg:
                status_code = 502
            elif "SSL 인증서" in error_msg:
                status_code = 502
            elif "API 응답 형식" in error_msg:
                status_code = 502
            return JsonResponse({'status': 'error', 'message': error_msg}, status=status_code)
        else:
            print("Success! Returning places summary list.")
            # 'places' 키는 프론트엔드와 일관성을 위해 유지
            return JsonResponse({'status': 'success', 'places': places_summary_list})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        print(f"Unexpected error in receive_location view: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)
