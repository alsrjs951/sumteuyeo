import json
import requests # 외부 API 호출을 위한 라이브러리
import re # 홈페이지 URL 파싱을 위한 정규표현식 라이브러리
import ssl # SSL 컨텍스트 조정을 위해 추가
from requests.adapters import HTTPAdapter # 커스텀 어댑터를 위해 추가

# urllib3 임포트 (requests 버전에 따라 경로 다를 수 있음)
try:
    # urllib3 1.x 버전대
    from requests.packages.urllib3.poolmanager import PoolManager
    from requests.packages.urllib3.util.ssl_ import create_urllib3_context
except ImportError:
    # urllib3 2.x 버전대 (최신 requests 는 보통 이쪽)
    from urllib3.poolmanager import PoolManager
    from urllib3.util.ssl_ import create_urllib3_context

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie # CSRF 쿠키 설정을 위해
from django.views.decorators.http import require_POST # POST 요청만 받도록 설정
from django.shortcuts import render # HTML 템플릿 렌더링을 위해
from django.conf import settings # settings.py의 설정 값을 가져오기 위해


# --- Custom HTTP Adapter for Cipher Suite ---
class CustomCipherAdapter(HTTPAdapter):
    """HTTPS 연결 시 기본 암호화 스위트 설정을 조정하는 어댑터"""
    def init_poolmanager(self, connections, maxsize, block=False):
        # 기본 SSL 컨텍스트 생성 시도
        context = create_urllib3_context()
        try:
            # 시스템 기본값보다 약간 완화된 보안 레벨 적용 시도
            context.set_ciphers('DEFAULT:@SECLEVEL=1')
            print("CustomCipherAdapter: Applied 'DEFAULT:@SECLEVEL=1' cipher setting.") # 적용 확인용 로그
        except Exception as e:
            print(f"Warning: Could not set custom ciphers ('DEFAULT:@SECLEVEL=1'): {e}")
            # 암호화 스위트 설정 실패 시 기본 컨텍스트 사용
            pass

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            ssl_context=context
        )


# --- Helper Function: 주변 관광지 정보 가져오기 ---
def get_nearby_places(latitude, longitude, api_key):
    """
    주어진 위도, 경도를 기반으로 TourAPI를 호출하여
    주변 관광지 정보(개요, 홈페이지 포함) 리스트를 반환합니다.
    requests.Session과 CustomCipherAdapter를 사용합니다.

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

    # --- requests.Session 생성 및 커스텀 어댑터 마운트 ---
    session = requests.Session()
    session.mount('https://', CustomCipherAdapter()) # HTTPS 요청에 커스텀 어댑터 적용
    # ------------------------------------------------

    # --- 1. locationBasedList1 API 호출 (주변 관광지 목록 가져오기) ---
    location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    location_params = {
        'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'mapX': longitude, 'mapY': latitude, 'radius': 20000,
        'listYN': 'Y', 'arrange': 'E', 'contentTypeId': 12, 'numOfRows': 20, '_type': 'json'
    }

    try:

        # session.get 사용
        print("Attempting to call locationBasedList1 API (using Session with Custom Adapter)...") # 호출 시도 로그
        response_loc = session.get(location_api_url, params=location_params, timeout=10) # 타임아웃 증가 고려
        response_loc.raise_for_status()
        api_data_loc = response_loc.json()
        print("locationBasedList1 API call successful.") # 성공 로그

        if api_data_loc['response']['header']['resultCode'] != '0000':
            error_message = api_data_loc['response']['header'].get('resultMsg', '위치 기반 API 오류')
            print(f"TourAPI Error (locationBasedList1): {error_message}")
            # 실패 시 세션 닫고 반환
            session.close()
            return [], f'주변 관광지 목록 API 오류: {error_message}'

        items_data = api_data_loc['response']['body'].get('items', {})
        items = items_data.get('item', [])

        # --- 2. 각 관광지의 상세 정보 가져오기 (detailCommon1 호출) ---
        if items:
            detail_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"
            print(f"Found {len(items)} items. Fetching details (using Session with Custom Adapter)...") # 상세 정보 조회 시작 로그

            for i, item in enumerate(items): # 진행 상황 로그를 위해 enumerate 사용
                content_id = item.get('contentid')
                if not content_id: continue

                # print(f"  [{i+1}/{len(items)}] Fetching details for contentId: {content_id}") # 로그 너무 많으면 주석 처리
                detail_params = {
                    'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
                    'contentId': content_id, '_type': 'json', 'defaultYN': 'Y',
                    'firstImageYN': 'N', 'areacodeYN': 'N', 'catcodeYN': 'N',
                    'addrinfoYN': 'N', 'mapinfoYN': 'N', 'overviewYN': 'Y', 'homepageYN': 'Y'
                }

                overview = ''
                homepage_url = ''

                try:
                    # session.get 사용
                    response_detail = session.get(detail_api_url, params=detail_params, timeout=5) # 타임아웃 증가 고려
                    response_detail.raise_for_status()
                    api_data_detail = response_detail.json()

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
                                else: homepage_url = ''
                    else:
                        detail_error = api_data_detail['response']['header'].get('resultMsg', '상세 정보 API 오류')
                        # print(f"  TourAPI Warning (detailCommon1 for contentId {content_id}): {detail_error}") # 로그 너무 많으면 주석 처리

                except requests.exceptions.Timeout:
                     print(f"  API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
                except requests.exceptions.RequestException as e:
                     print(f"  API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")
                     # 여기서 발생한 오류가 전체를 중단시키지 않도록 주의

                places.append({
                    'title': item.get('title', '이름 없음'),
                    'addr': item.get('addr1', ''),
                    'image': item.get('firstimage', ''),
                    'overview': overview,
                    'homepage': homepage_url
                })
            print("Finished fetching details.") # 상세 정보 조회 완료 로그

        session.close() # 세션 닫기
        return places, None # 최종 성공 시 places 리스트와 None 반환

    except requests.exceptions.Timeout as e: # 위치 기반 API 타임아웃
        error_message = '주변 관광 정보 요청 시간이 초과되었습니다.'
        print(f"API 요청 시간 초과 (locationBasedList1): {e}")
        session.close() # 오류 발생 시에도 세션 닫기
        return [], error_message
    except requests.exceptions.RequestException as e: # 위치 기반 API 네트워크/SSL 오류
        error_message = '주변 관광 정보를 가져오는 중 네트워크 오류가 발생했습니다.'
        print(f"API 요청 오류 (locationBasedList1): {e}")
        session.close() # 오류 발생 시에도 세션 닫기
        return [], error_message
    except Exception as e: # JSON 파싱 오류 등 기타 예외
        error_message = '주변 관광 정보를 처리하는 중 오류가 발생했습니다.'
        print(f"처리 중 오류 (locationBasedList1 or detail): {e}")
        # finally 블록 대신 여기서도 세션을 닫아주는 것이 안전할 수 있음
        try:
            session.close()
        except NameError: # session 이 정의되기 전에 오류난 경우
            pass
        except Exception: # 닫기 중 다른 오류
            pass
        return [], error_message
    # finally 블록은 NameError 가능성 때문에 제거하고 각 except 에서 close() 호출 고려


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
            status_code = 500
            if "시간 초과" in error_msg: status_code = 504
            elif "네트워크 오류" in error_msg or "API 오류" in error_msg : status_code = 502
            return JsonResponse({'status': 'error', 'message': error_msg}, status=status_code)
        else:
            print("Success! Returning places list.") # 최종 성공 로그
            return JsonResponse({'status': 'success', 'places': places_list})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        print(f"Unexpected error in receive_location view: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)