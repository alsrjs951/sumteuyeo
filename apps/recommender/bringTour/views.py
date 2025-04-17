# yourapp/views.py

import json
import requests # 외부 API 호출을 위한 라이브러리
# from urllib.parse import quote # 서비스 키 인코딩이 필요할 경우 사용 (requests가 params로 처리하면 보통 불필요)

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
    return render(request, 'yourapp/location_page.html')

# 프론트엔드로부터 AJAX POST 요청으로 위치 정보를 받아
# TourAPI를 호출하고 주변 관광지 정보를 JSON으로 반환하는 API 뷰
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

        # --- TourAPI 호출 로직 시작 ---

        # settings.py에서 API 키 값을 불러옵니다.
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

        # 한국관광공사 TourAPI 'locationBasedList1' 엔드포인트 URL
        api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"

        # API 요청에 필요한 파라미터 설정
        params = {
            'serviceKey': TOUR_API_KEY,     # settings에서 불러온 API 키
            'MobileOS': 'ETC',              # 필수 파라미터 (플랫폼 구분)
            'MobileApp': 'YourAppName',     # 필수 파라미터 (앱/서비스 이름 - 실제 이름으로 변경 권장)
            'mapX': longitude,              # 경도 (API 요구사항에 맞춘 파라미터 이름)
            'mapY': latitude,               # 위도 (API 요구사항에 맞춘 파라미터 이름)
            'radius': 20000,                # 검색 반경 (단위: m) - 20km
            'listYN': 'Y',                  # 목록 구분 (Y=목록, N=개수)
            'arrange': 'E',                 # 정렬 구분 (A=제목순, B=조회순, C=수정일순, D=생성일순, E=거리순)
            'contentTypeId': 12,            # 콘텐츠 타입 ID (12:관광지) - 필요시 다른 타입 ID 사용 가능
            'numOfRows': 20,                # 한 페이지 결과 수 (API 최대값 및 필요에 따라 조절)
            '_type': 'json'                 # 응답 데이터 형식 (JSON)
        }

        # requests 라이브러리를 사용하여 API 호출
        try:
            # GET 요청 전송, 타임아웃 5초 설정
            response = requests.get(api_url, params=params, timeout=5)
            # HTTP 오류(4xx, 5xx) 발생 시 예외 발생
            response.raise_for_status()

            # 응답받은 JSON 데이터 파싱
            api_data = response.json()

            # API 응답 성공 여부 확인 (헤더의 resultCode 기준)
            if api_data['response']['header']['resultCode'] == '0000':
                # 데이터가 없는 경우 'items' 또는 'item' 키가 없을 수 있으므로 .get()으로 안전하게 접근
                items_data = api_data['response']['body'].get('items', {}) # 'items'가 없으면 빈 딕셔너리
                items = items_data.get('item', []) # 'item'이 없거나 'items'가 비었으면 빈 리스트

                # 프론트엔드로 전달할 관광지 정보 리스트 생성
                places = []
                if items: # 결과 아이템이 있을 때만 처리
                    for item in items:
                        places.append({
                            'title': item.get('title', '이름 없음'), # title이 없는 경우 대비
                            'addr': item.get('addr1', ''),         # addr1이 없는 경우 대비 (주소)
                            'image': item.get('firstimage', '')    # firstimage가 없는 경우 대비 (대표 이미지 URL)
                        })

                # 성공 응답 반환 (status와 함께 장소 리스트 포함)
                return JsonResponse({'status': 'success', 'places': places})
            else:
                # API 자체 에러 (TourAPI 응답 헤더에 오류 메시지가 있음)
                error_message = api_data['response']['header'].get('resultMsg', '알 수 없는 API 오류')
                print(f"TourAPI Error: {error_message} (Code: {api_data['response']['header']['resultCode']})")
                # 사용자에게는 좀 더 일반적인 메시지 전달
                return JsonResponse({'status': 'error', 'message': f'관광 정보를 가져오는 중 API 오류가 발생했습니다.'}, status=500)

        except requests.exceptions.Timeout:
            # 타임아웃 발생 시
            print("API 요청 시간 초과")
            return JsonResponse({'status': 'error', 'message': '관광 정보 요청 시간이 초과되었습니다.'}, status=504) # 504 Gateway Timeout
        except requests.exceptions.RequestException as e:
            # 기타 네트워크 관련 오류 (연결 실패, HTTP 오류 등)
            print(f"API 요청 오류: {e}")
            return JsonResponse({'status': 'error', 'message': '관광 정보를 가져오는 중 오류가 발생했습니다. (네트워크 문제)'}, status=502) # 502 Bad Gateway

        # --- TourAPI 호출 로직 끝 ---

    except json.JSONDecodeError:
        # 프론트엔드에서 보낸 요청 본문의 JSON 형식이 잘못되었을 경우
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        # 위에서 처리하지 못한 그 외 모든 예외 처리
        # 실제 운영 환경에서는 어떤 종류의 에러인지 로깅하는 것이 중요합니다.
        print(f"서버 내부 오류 발생: {e}")
        # 사용자에게는 상세 오류 내용을 노출하지 않는 것이 좋습니다.
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)