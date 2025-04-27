import json
import requests # 외부 API 호출을 위한 라이브러리
import re # 홈페이지 URL 파싱을 위한 정규표현식 라이브러리
# from urllib.parse import quote # 필요시 사용

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie # CSRF 쿠키 설정을 위해
from django.views.decorators.http import require_POST # POST 요청만 받도록 설정
from django.shortcuts import render # HTML 템플릿 렌더링을 위해
from django.conf import settings # settings.py의 설정 값을 가져오기 위해

# HTML 페이지를 보여주는 뷰 (프론트엔드 코드가 담긴 템플릿 렌더링)
@ensure_csrf_cookie # 이 뷰가 렌더링될 때 CSRF 쿠키를 설정하도록 보장
def location_page_view(request):
    # 'yourapp/location_page.html' 템플릿을 렌더링합니다.
    # templates 폴더 구조에 맞게 경로를 확인하세요. (예: templates/yourapp/location_page.html)
    return render(request, 'Sumteuyeo/location_page.html')

# 프론트엔드로부터 AJAX POST 요청으로 위치 정보를 받아
# TourAPI를 호출하고 주변 관광지 정보 + 상세 정보(개요, 홈페이지)를 JSON으로 반환하는 API 뷰
@require_POST # 이 뷰는 POST 요청만 허용
def receive_location(request):
    try:
        # 요청 본문(body)에서 JSON 데이터를 파싱합니다.
        data = json.loads(request.body)
        # 프론트엔드에서 'latitude', 'longitude' 이름으로 보낸 값을 받습니다.
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        # 위도, 경도 값이 제대로 들어왔는지 확인
        if latitude is None or longitude is None:
            return JsonResponse({'status': 'error', 'message': '필수 파라미터(latitude, longitude)가 누락되었습니다.'}, status=400)

        # --- API 키 로드 ---
        try:
            # settings.py 파일에 TOUR_API_KEY='YOUR_KEY' 형식으로 정의되어 있어야 합니다.
            TOUR_API_KEY = settings.TOUR_API_KEY
            if not TOUR_API_KEY: # 키 값이 비어있는 경우 에러 처리
                raise AttributeError # 키가 비어있으면 AttributeError를 발생시켜 아래 except 블록에서 처리
        except AttributeError:
             # settings.py 에 TOUR_API_KEY 가 정의되지 않았거나 비어있는 경우
             error_msg = "settings.py에 TOUR_API_KEY가 정의되지 않았거나 비어있습니다."
             print(f"설정 오류: {error_msg}")
             # 사용자에게는 상세 오류 대신 일반적인 메시지를 전달하는 것이 좋을 수 있습니다.
             return JsonResponse({'status': 'error', 'message': 'API 키 설정에 문제가 발생했습니다.'}, status=500)

        # --- 1. locationBasedList1 API 호출 (주변 관광지 목록 가져오기) ---
        location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
        location_params = {
            'serviceKey': TOUR_API_KEY, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo', # YourAppName은 실제 서비스명으로 변경 권장
            'mapX': longitude, 'mapY': latitude, 'radius': 20000,
            'listYN': 'Y', 'arrange': 'E', 'contentTypeId': 12, 'numOfRows': 20, '_type': 'json'
        }

        try:
            # 주변 관광지 목록 API 호출
            response_loc = requests.get(location_api_url, params=location_params, timeout=5)
            response_loc.raise_for_status() # HTTP 에러 발생 시 예외 처리
            api_data_loc = response_loc.json()

            # 주변 관광지 목록 API 응답 코드 확인
            if api_data_loc['response']['header']['resultCode'] != '0000':
                error_message = api_data_loc['response']['header'].get('resultMsg', '위치 기반 API 오류')
                print(f"TourAPI Error (locationBasedList1): {error_message}")
                return JsonResponse({'status': 'error', 'message': '주변 관광지 목록을 가져오는 중 API 오류가 발생했습니다.'}, status=500)

            # 주변 관광지 아이템 목록 추출 (없을 경우 대비)
            items_data = api_data_loc['response']['body'].get('items', {})
            items = items_data.get('item', [])

            # --- 2. 각 관광지의 상세 정보 (개요, 홈페이지) 가져오기 (detailCommon1 호출) ---
            places = [] # 최종 결과를 담을 리스트
            if items: # 주변 관광지 목록이 있을 경우에만 상세 정보 조회 시도
                detail_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"

                for item in items:
                    content_id = item.get('contentid')
                    if not content_id: continue # contentId가 없는 아이템은 건너뛰기

                    # 상세 정보 API 호출 파라미터 설정
                    detail_params = {
                        'serviceKey': TOUR_API_KEY, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
                        'contentId': content_id,
                        '_type': 'json',
                        'defaultYN': 'Y',       # 기본 정보 포함 여부
                        'firstImageYN': 'N',    # 대표 이미지는 locationBasedList1 결과 사용 예정이므로 N
                        'areacodeYN': 'N',      # 지역코드 불필요
                        'catcodeYN': 'N',       # 카테고리 코드 불필요
                        'addrinfoYN': 'N',      # 주소 정보 불필요 (locationBasedList1 결과 사용)
                        'mapinfoYN': 'N',       # 지도 정보 불필요
                        'overviewYN': 'Y',      # *** 개요 정보 포함 (Y) ***
                        'homepageYN': 'Y'       # *** 홈페이지 정보 포함 (Y) ***
                    }

                    overview = ''       # 개요 정보 기본값
                    homepage_url = ''   # 홈페이지 URL 기본값

                    try:
                        # 각 관광지별 상세 정보 API 호출 (타임아웃 3초)
                        response_detail = requests.get(detail_api_url, params=detail_params, timeout=3)
                        response_detail.raise_for_status() # HTTP 에러 발생 시 예외 처리
                        api_data_detail = response_detail.json()

                        # 상세 정보 API 응답 코드 확인
                        if api_data_detail['response']['header']['resultCode'] == '0000':
                            # 상세 정보 아이템 추출 (없을 경우 대비)
                            detail_items_data = api_data_detail['response']['body'].get('items', {})
                            detail_item = detail_items_data.get('item') # 상세 정보는 보통 item이 하나

                            # API 명세상 item이 리스트로 올 수도 있다고 가정하고 처리
                            if detail_item and isinstance(detail_item, list):
                                detail_item = detail_item[0] # 리스트면 첫번째 요소 사용

                            if detail_item and isinstance(detail_item, dict): # 객체 형태인지 최종 확인
                                overview = detail_item.get('overview', '') # 개요 정보 추출
                                homepage_raw = detail_item.get('homepage', '') # 홈페이지 정보 (HTML 태그 포함 가능)

                                # 홈페이지 정보에서 URL만 추출 시도
                                if homepage_raw:
                                    # 정규표현식으로 href 속성 값 추출 (간단한 경우)
                                    match = re.search(r'href=[\'"]?([^\'" >]+)', homepage_raw, re.IGNORECASE)
                                    if match:
                                        homepage_url = match.group(1) # 추출된 URL 사용
                                    else:
                                        # URL 추출 실패 시, 원본을 그대로 쓰거나 비워둘 수 있음 (여기선 비워둠)
                                        # homepage_url = homepage_raw # 원본 사용 옵션
                                        homepage_url = '' # 실패 시 빈 값 처리 옵션
                        else:
                            # 특정 관광지의 상세 정보 조회 실패 시 로그 남기기 (전체 실패 아님)
                            error_message = api_data_detail['response']['header'].get('resultMsg', '상세 정보 API 오류')
                            print(f"TourAPI Warning (detailCommon1 for contentId {content_id}): {error_message} (Code: {api_data_detail['response']['header']['resultCode']})")

                    except requests.exceptions.Timeout:
                        # 상세 정보 API 타임아웃 시 로그 남기기
                        print(f"API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
                    except requests.exceptions.RequestException as e:
                        # 상세 정보 API 네트워크 오류 시 로그 남기기
                        print(f"API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")
                    # 특정 상세 정보 조회 실패는 전체 에러로 간주하지 않고 넘어감 (overview, homepage는 빈 값 유지)

                    # 최종 정보 조합 (locationBasedList1 정보 + detailCommon1 정보)
                    places.append({
                        'title': item.get('title', '이름 없음'),   # 이름 (locationBasedList1)
                        'addr': item.get('addr1', ''),            # 주소 (locationBasedList1)
                        'image': item.get('firstimage', ''),      # 대표 이미지 (locationBasedList1)
                        'overview': overview,                     # 개요 (detailCommon1)
                        'homepage': homepage_url                  # 홈페이지 URL (detailCommon1, 파싱됨)
                    })

            # 최종 결과 반환
            return JsonResponse({'status': 'success', 'places': places})

        except requests.exceptions.Timeout:
            # 위치 기반 API 타임아웃 시
            print("API 요청 시간 초과 (locationBasedList1)")
            return JsonResponse({'status': 'error', 'message': '주변 관광 정보 요청 시간이 초과되었습니다.'}, status=504) # 504 Gateway Timeout
        except requests.exceptions.RequestException as e:
            # 위치 기반 API 네트워크 오류 시
            print(f"API 요청 오류 (locationBasedList1): {e}")
            return JsonResponse({'status': 'error', 'message': '주변 관광 정보를 가져오는 중 오류가 발생했습니다.'}, status=502) # 502 Bad Gateway

    except json.JSONDecodeError:
        # 요청 본문 JSON 파싱 오류 시
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        # 그 외 모든 예상치 못한 오류 처리
        print(f"서버 내부 오류 발생: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)