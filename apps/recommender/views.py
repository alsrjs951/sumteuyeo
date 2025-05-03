import json
import requests # 외부 API 호출을 위한 라이브러리
import re # 홈페이지 URL 파싱을 위한 정규표현식 라이브러리

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie # CSRF 쿠키 설정을 위해
from django.views.decorators.http import require_POST # POST 요청만 받도록 설정
from django.shortcuts import render # HTML 템플릿 렌더링을 위해
from django.conf import settings # settings.py의 설정 값을 가져오기 위해

# --- 주변 관광지 가져오는 함수 ---
def get_nearby_places(latitude, longitude, api_key):
    """
    주어진 위도, 경도를 기반으로 TourAPI를 호출,
    주변 관광지 정보(개요, 홈페이지 포함) 리스트를 반환.

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

    # --- 1. locationBasedList1 API 호출 (주변 관광지 목록 가져오기) ---
    location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    location_params = {
        'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'mapX': longitude, 'mapY': latitude, 'radius': 20000,
        'listYN': 'Y', 'arrange': 'E', 'contentTypeId': 12, 'numOfRows': 20, '_type': 'json'
    }

    try:
        response_loc = requests.get(location_api_url, params=location_params, timeout=5)
        response_loc.raise_for_status()
        api_data_loc = response_loc.json()

        if api_data_loc['response']['header']['resultCode'] != '0000':
            error_message = api_data_loc['response']['header'].get('resultMsg', '위치 기반 API 오류')
            print(f"TourAPI Error (locationBasedList1): {error_message}")
            return [], f'주변 관광지 목록 API 오류: {error_message}' # 실패 시 빈 리스트와 에러 메시지 반환

        items_data = api_data_loc['response']['body'].get('items', {})
        items = items_data.get('item', [])

        # --- 2. 각 관광지의 상세 정보 (개요, 홈페이지) 가져오기 (detailCommon1 호출) ---
        if items:
            detail_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"

            for item in items:
                content_id = item.get('contentid')
                if not content_id: continue

                detail_params = {
                    'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
                    'contentId': content_id, '_type': 'json', 'defaultYN': 'Y',
                    'firstImageYN': 'N', 'areacodeYN': 'N', 'catcodeYN': 'N',
                    'addrinfoYN': 'N', 'mapinfoYN': 'N', 'overviewYN': 'Y', 'homepageYN': 'Y'
                }

                overview = ''
                homepage_url = ''

                try:
                    response_detail = requests.get(detail_api_url, params=detail_params, timeout=3)
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
                                else: homepage_url = '' # 파싱 실패 시 빈 값
                    else:
                        # 상세 정보 조회 실패는 개별 로그만 남기고 전체 에러 처리 안함
                        detail_error = api_data_detail['response']['header'].get('resultMsg', '상세 정보 API 오류')
                        print(f"TourAPI Warning (detailCommon1 for contentId {content_id}): {detail_error}")

                except requests.exceptions.Timeout:
                     print(f"API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
                except requests.exceptions.RequestException as e:
                     print(f"API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")

                # 정보 조합하여 리스트에 추가
                places.append({
                    'title': item.get('title', '이름 없음'),
                    'addr': item.get('addr1', ''),
                    'image': item.get('firstimage', ''),
                    'overview': overview,
                    'homepage': homepage_url
                })

        # 성공 시 최종 places 리스트와 None (오류 없음) 반환
        return places, None

    except requests.exceptions.Timeout:
        error_message = '주변 관광 정보 요청 시간이 초과되었습니다.'
        print(f"API 요청 시간 초과 (locationBasedList1): {error_message}")
        return [], error_message # 실패 시 빈 리스트와 에러 메시지 반환
    except requests.exceptions.RequestException as e:
        error_message = '주변 관광 정보를 가져오는 중 네트워크 오류가 발생했습니다.'
        print(f"API 요청 오류 (locationBasedList1): {e}")
        return [], error_message # 실패 시 빈 리스트와 에러 메시지 반환
    except Exception as e: # JSON 파싱 오류 등 기타 예외
        error_message = '주변 관광 정보를 처리하는 중 오류가 발생했습니다.'
        print(f"처리 중 오류 (locationBasedList1 or detail): {e}")
        return [], error_message # 실패 시 빈 리스트와 에러 메시지 반환


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
        places_list, error_msg = get_nearby_places(latitude, longitude, TOUR_API_KEY)

        # --- 결과에 따른 응답 생성 ---
        if error_msg:
            # 함수 실행 중 오류 발생 시
            return JsonResponse({'status': 'error', 'message': error_msg}, status=500) # 또는 상황에 맞는 상태 코드
        else:
            # 성공 시
            return JsonResponse({'status': 'success', 'places': places_list})

    except json.JSONDecodeError:
        # 요청 본문 JSON 파싱 오류 시
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        # 그 외 모든 예상치 못한 오류 처리
        print(f"뷰 처리 중 오류 발생: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)