import json
import requests # 외부 API 호출을 위한 라이브러리
import re # 홈페이지 URL 파싱을 위한 정규표현식 라이브러리
import certifi # SSL 인증서 경로를 명시적으로 사용하기 위해 추가
import time

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie # CSRF 쿠키 설정을 위해
from django.views.decorators.http import require_POST # POST 요청만 받도록 설정
from django.shortcuts import render # HTML 템플릿 렌더링을 위해
from django.conf import settings # settings.py의 설정 값을 가져오기 위해


# --- Helper Function: 주변 관광지 정보 가져오기 (verify 경로 명시) ---
def get_nearby_places(latitude, longitude, api_key):
    """
    주어진 위도, 경도를 기반으로 TourAPI를 호출하여
    주변 관광지 정보(개요, 홈페이지 포함) 리스트를 반환합니다.
    requests.get 호출 시 verify 경로를 명시하고, detailCommon1 호출 사이에 지연을 둡니다.

    Args:
        latitude (float): 사용자 위도
        longitude (float): 사용자 경도
        api_key (str): TourAPI 인증키

    Returns:
        tuple: (places_list, error_message)
               성공 시 (list, None), 실패 시 ([], str) 형태
    """
    places = []
    error_message = None

    # certifi CA 번들 경로 가져오기
    try:
        ca_bundle_path = certifi.where()
        print(f"Explicitly using CA bundle: {ca_bundle_path}")
    except Exception as e:
        print(f"Error getting certifi path: {e}")
        error_message = "certifi CA 번들 경로를 찾는 중 오류가 발생했습니다."
        return [], error_message

    # --- 1. locationBasedList1 API 호출 (주변 관광지 목록 가져오기) ---
    location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    location_params = {
        'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'mapX': longitude, 'mapY': latitude, 'radius': 20000,
        'listYN': 'Y', 'arrange': 'E', 'contentTypeId': 12, 'numOfRows': 20, '_type': 'json'
    }

    response_loc = None # 응답 객체 초기화
    try:
        print("Attempting to call locationBasedList1 API (with explicit verify path)...")
        # requests.get 호출 시 verify 파라미터 추가
        response_loc = requests.get(
            location_api_url,
            params=location_params,
            timeout=10, # 타임아웃 증가 고려
            verify=ca_bundle_path # certifi 경로 명시적 지정
        )
        response_loc.raise_for_status() # HTTP 오류 발생 시 예외 발생
        api_data_loc = response_loc.json() # JSON 파싱 시도
        print("locationBasedList1 API call successful (with explicit verify path).") # 성공 로그

        # locationBasedList1 응답 코드 확인
        if api_data_loc['response']['header']['resultCode'] != '0000':
            error_message = api_data_loc['response']['header'].get('resultMsg', '위치 기반 API 오류')
            print(f"TourAPI Error (locationBasedList1): {error_message}")
            return [], f'주변 관광지 목록 API 오류: {error_message}'

        items_data = api_data_loc['response']['body'].get('items', {})
        items = items_data.get('item', [])

        # --- 2. 각 관광지의 상세 정보 가져오기 (detailCommon1 호출) ---
        if items:
            detail_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"
            print(f"Found {len(items)} items. Fetching details (with explicit verify path)...") # 상세 정보 조회 시작 로그

            for i, item in enumerate(items): # 진행 상황 로그를 위해 enumerate 사용
                content_id = item.get('contentid')
                if not content_id: continue

                # print(f"  [{i+1}/{len(items)}] Fetching details for contentId: {content_id}") # 로그 너무 많으면 주석 처리
                detail_params = {
                    'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
                    'contentId': content_id, '_type': 'json', 'defaultYN': 'Y',
                    'firstImageYN': 'N', 'areacodeYN': 'N', 'catcodeYN': 'N',
                    'addrinfoYN': 'N', 'mapinfoYN': 'N', 'overviewYN': 'Y',
                    #'homepageYN': 'N'
                }

                overview = ''
                homepage_url = ''
                response_detail_text = '' # 응답 텍스트 저장용 변수
                response_detail = None # 응답 객체 초기화

                try:
                    # requests.get 호출 시 verify 파라미터 추가
                    response_detail = requests.get(
                        detail_api_url,
                        params=detail_params,
                        timeout=5, # 타임아웃 증가 고려
                        verify=ca_bundle_path # certifi 경로 명시적 지정
                    )
                    response_detail_text = response_detail.text # JSON 파싱 전 텍스트 저장
                    response_detail.raise_for_status() # HTTP 오류 체크

                    # --- 응답 내용 확인용 로그 추가 ---
                    print(f"  ContentId {content_id} - Status Code: {response_detail.status_code}")
                    print(f"  ContentId {content_id} - Response Text Preview: {response_detail_text[:200]}")
                    # --------------------------------

                    # JSON 파싱 시도
                    api_data_detail = response_detail.json()

                    # detailCommon1 응답 코드 확인
                    if api_data_detail['response']['header']['resultCode'] == '0000':
                        detail_items_data = api_data_detail['response']['body'].get('items', {})
                        detail_item = detail_items_data.get('item')
                        if detail_item and isinstance(detail_item, list): detail_item = detail_item[0]

                        if detail_item and isinstance(detail_item, dict):
                            overview = detail_item.get('overview', '')
                            homepage_raw = detail_item.get('homepage', '')
                            if homepage_raw:
                                match = re.search(r'href=[\'"]?([^\'" >]+)', homepage_raw, re.IGNORECASE)
                                if match: homepage_url = match.group(1)
                                else: homepage_url = '' # 파싱 실패 시 빈 값
                    else:
                        detail_error = api_data_detail['response']['header'].get('resultMsg', '상세 정보 API 오류')
                        print(f"  TourAPI Warning (detailCommon1 for contentId {content_id}, resultCode {api_data_detail['response']['header']['resultCode']}): {detail_error}")

                except requests.exceptions.SSLError as e: # SSLError 명시적 처리
                    print(f"  !!! SSLError occurred (detailCommon1 for contentId {content_id}): {e}")
                except requests.exceptions.Timeout:
                     print(f"  API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
                except requests.exceptions.RequestException as e: # HTTP 오류 포함 기타 요청 오류
                     print(f"  API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")
                     if response_detail is not None: # 응답 객체가 있으면 상태 코드 로깅
                         print(f"  Response Status Code was: {response_detail.status_code}")
                except json.JSONDecodeError as e: # JSON 파싱 오류
                    print(f"  JSON Decode Error (detailCommon1 for contentId {content_id}): {e}")
                    # JSON 오류 시 실제 받은 텍스트 전체 출력 (길 수 있음)
                    if response_detail is not None:
                         print(f"  Received non-JSON response text: {response_detail_text}")
                except Exception as e: # 그 외 다른 예외
                    print(f"  Unexpected error processing detail for contentId {content_id}: {e}")

                # 정보 조합하여 리스트에 추가 (상세 정보 조회 실패 시 overview, homepage는 빈 값)
                places.append({
                    'title': item.get('title', '이름 없음'),
                    'addr': item.get('addr1', ''),
                    'image': item.get('firstimage', ''),
                    'overview': overview,
                    'homepage': homepage_url
                })

                # --- 시간 지연 추가 ---
                # 마지막 아이템 요청 후에는 지연 불필요
                if i < len(items) - 1:
                     delay = 0.2 # 0.2초 대기 (API 서버 상태에 따라 조절 필요)
                     print(f"  Sleeping for {delay} seconds...")
                     time.sleep(delay)
                # ------------------

            print("Finished fetching details.") # 상세 정보 조회 완료 로그

        # 최종 성공 시 places 리스트와 None (오류 없음) 반환
        return places, None

    except requests.exceptions.SSLError as e: # 첫 API 호출의 SSLError 명시적 처리
        error_message = 'SSL 인증서 검증 오류가 발생했습니다.'
        print(f"!!! SSLError occurred (locationBasedList1): {e}")
        return [], error_message
    except requests.exceptions.Timeout as e: # 위치 기반 API 타임아웃
        error_message = '주변 관광 정보 요청 시간이 초과되었습니다.'
        print(f"API 요청 시간 초과 (locationBasedList1): {e}")
        return [], error_message
    except requests.exceptions.RequestException as e: # 위치 기반 API 기타 네트워크 오류
        error_message = '주변 관광 정보를 가져오는 중 네트워크 오류가 발생했습니다.'
        print(f"API 요청 오류 (locationBasedList1): {e}")
        if response_loc is not None: # 응답 객체가 있으면 상태 코드 로깅
            print(f"Response Status Code was: {response_loc.status_code}")
        return [], error_message
    except json.JSONDecodeError as e: # 첫 API 호출의 JSON 파싱 오류
        error_message = '주변 관광 정보 API 응답 형식이 잘못되었습니다.'
        print(f"JSON Decode Error (locationBasedList1): {e}")
        if response_loc is not None: # 응답 객체가 있으면 텍스트 로깅
            print(f"Received non-JSON response (locationBasedList1): {response_loc.text[:200]}")
        return [], error_message
    except Exception as e: # 기타 예외
        error_message = '주변 관광 정보를 처리하는 중 오류가 발생했습니다.'
        print(f"처리 중 오류 (locationBasedList1 or detail): {e}")
        return [], error_message


# --- Views ---

# HTML 페이지를 보여주는 뷰
@ensure_csrf_cookie
def location_page_view(request):
    return render(request, 'templates/core/main_page.html') # 템플릿 경로 확인

# 프론트엔드 AJAX 요청 처리 뷰
@require_POST
def receive_location(request):
    try:
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'status': 'error', 'message': '필수 파라미터(latitude, longitude)가 누락되었습니다.'}, status=400)

        # --- API 키 로드 ---
        try:
            TOUR_API_KEY = settings.TOUR_API_KEY
            if not TOUR_API_KEY: raise AttributeError
        except AttributeError:
             error_msg = "settings.py에 TOUR_API_KEY가 정의되지 않았거나 비어있습니다."
             print(f"설정 오류: {error_msg}")
             return JsonResponse({'status': 'error', 'message': 'API 키 설정에 문제가 발생했습니다.'}, status=500)

        # --- 분리된 함수 호출 ---
        print("Calling get_nearby_places function...") # 함수 호출 로그
        places_list, error_msg = get_nearby_places(latitude, longitude, TOUR_API_KEY)
        print(f"get_nearby_places returned. Error message: {error_msg}") # 함수 반환 로그

        # --- 결과에 따른 응답 생성 ---
        if error_msg:
            print(f"Error detected in receive_location: {error_msg}") # 최종 에러 확인 로그
            # 상태 코드는 오류 메시지 내용에 따라 더 세분화 가능
            status_code = 500 # 기본값: 서버 내부 오류
            if "시간 초과" in error_msg: status_code = 504 # Gateway Timeout
            elif "네트워크 오류" in error_msg or "API 오류" in error_msg : status_code = 502 # Bad Gateway
            elif "SSL 인증서" in error_msg: status_code = 502 # SSL 문제도 게이트웨이 오류로 간주 가능
            elif "API 응답 형식" in error_msg: status_code = 502
            return JsonResponse({'status': 'error', 'message': error_msg}, status=status_code)
        else:
            # 성공 시
            print("Success! Returning places list.") # 최종 성공 로그
            return JsonResponse({'status': 'success', 'places': places_list})

    except json.JSONDecodeError:
        # 요청 본문 JSON 파싱 오류 시
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        # 그 외 모든 예상치 못한 오류 처리
        print(f"Unexpected error in receive_location view: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)