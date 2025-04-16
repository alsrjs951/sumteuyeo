import json
import requests
from urllib.parse import quote

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.shortcuts import render
from django.conf import settings # Django 설정 객체 임포트

# ... location_page_view 함수 ...

@require_POST
def receive_location(request):
    try:
        data = json.loads(request.body)
        # 프론트엔드에서 넘어온 변수 이름은 latitude, longitude 로 유지
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'status': 'error', 'message': '필수 파라미터(latitude, longitude)가 누락되었습니다.'}, status=400)

        # --- TourAPI 호출 로직 ---
        try:
            TOUR_API_KEY = settings.TOUR_API_KEY
            if not TOUR_API_KEY:
                raise AttributeError
        except AttributeError:
             print("오류: settings.py에 TOUR_API_KEY가 정의되지 않았거나 비어있습니다.")
             return JsonResponse({'status': 'error', 'message': 'API 키 설정 오류가 발생했습니다.'}, status=500)

        api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"

        # *** 파라미터 이름 수정 ***
        params = {
            'serviceKey': TOUR_API_KEY,
            'MobileOS': 'ETC',
            'MobileApp': 'YourAppName', # 실제 앱 이름이나 서비스 이름으로 변경
            'mapX': longitude,       # 경도 값을 'mapX' 파라미터로 전달
            'mapY': latitude,        # 위도 값을 'mapY' 파라미터로 전달
            'radius': 20000,         # 반경 20000m (20km) 값을 'radius' 파라미터로 전달
            'listYN': 'Y',
            'arrange': 'E',          # 거리순 정렬
            'contentTypeId': 12,     # 관광지
            'numOfRows': 20,
            '_type': 'json'
        }

        # ... (requests.get 호출 및 응답 처리 로직 - 이전과 동일) ...
        try:
            response = requests.get(api_url, params=params, timeout=5)
            response.raise_for_status()
            api_data = response.json()

            if api_data['response']['header']['resultCode'] == '0000':
                items = api_data['response']['body'].get('items', {}).get('item', [])
                places = []
                if items:
                    for item in items:
                        places.append({
                            'title': item.get('title', '이름 없음'),
                            'addr': item.get('addr1', ''),
                            'image': item.get('firstimage', '')
                        })
                return JsonResponse({'status': 'success', 'places': places})
            else:
                error_message = api_data['response']['header'].get('resultMsg', '알 수 없는 API 오류')
                print(f"TourAPI Error: {error_message}")
                return JsonResponse({'status': 'error', 'message': f'API 오류: {error_message}'}, status=500)

        except requests.exceptions.RequestException as e:
            print(f"API 요청 오류: {e}")
            return JsonResponse({'status': 'error', 'message': '관광 정보를 가져오는 중 오류가 발생했습니다. (네트워크 문제)'}, status=502)

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        print(f"서버 내부 오류: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)