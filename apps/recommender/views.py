import json
import requests
import re
import certifi

from django.http import JsonResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import render
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from datetime import datetime
from django.db.models import Prefetch
from .services.theme_recommender import ThemeRecommender
from django.core.cache import cache
import random
import time
import logging

logger = logging.getLogger(__name__)

class MainRecommendationAPI(APIView):
    permission_classes = [permissions.AllowAny]
    CACHE_TIMEOUT = 600  # 10분 (초 단위)
    CACHE_PREFIX = "rec"

    def get(self, request):
        try:
            # 위치 파라미터 검증
            user_lat = float(request.query_params['lat'])
            user_lng = float(request.query_params['lng'])
        except (KeyError, ValueError) as e:
            logger.warning(f"잘못된 위치 파라미터: {str(e)}")
            return Response(
                {"status": "error", "message": "유효한 위경도 값이 필요합니다 (lat, lng 파라미터 필수)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 사용자 및 시간 정보
        user = request.user
        current_month = timezone.now().month  # 시간대 인식
        cache_key = self._generate_cache_key(user, current_month, user_lat, user_lng)

        # 캐시 체크
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f"캐시 히트: {cache_key}")
            return Response(cached_data, status=status.HTTP_200_OK)

        try:
            # 추천 엔진 실행
            recommendation_rows = ThemeRecommender.generate_recommendation_rows(
                user_id=user.id if user.is_authenticated else None,
                month=current_month,
                user_lat=user_lat,
                user_lng=user_lng
            )

            # 데이터 직렬화
            serialized_sections = self._serialize_recommendations(recommendation_rows)
            
            # 캐시 저장
            response_data = {
                "status": "success",
                "sections": serialized_sections
            }
            cache.set(cache_key, response_data, self.CACHE_TIMEOUT)
            logger.info(f"캐시 저장: {cache_key}")

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"추천 생성 실패: {str(e)}", exc_info=True)
            return Response(
                {"status": "error", "message": "추천 정보를 불러오는 데 실패했습니다."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

    def _generate_cache_key(self, user, month, lat, lng):
        """정밀한 캐시 키 생성"""
        user_id = user.id if user.is_authenticated else "anon"
        return f"{self.CACHE_PREFIX}:{user_id}:m{month}:{lat:.4f}:{lng:.4f}"

    def _serialize_recommendations(self, recommendation_rows):
        """섹션 구조 유지하며 직렬화"""
        seen_ids = set()  # 중복 콘텐츠 방지
        serialized = []

        for section_key, section_data in recommendation_rows.items():
            items = []
            for item in section_data['items']:
                content_id = item.detail.contentid
                if content_id not in seen_ids:
                    seen_ids.add(content_id)
                    items.append(self._serialize_content(item))
            
            # 무작위 순서 (시간 기반 시드)
            random.seed(int(time.time()) // 3600)  # 1시간마다 변경
            random.shuffle(items)

            serialized.append({
                "section_type": section_key,
                "title": section_data['title'],
                "items": items[:30]  # 최대 30개
            })

        return serialized

    def _serialize_content(self, content_feature):
        """개별 콘텐츠 직렬화"""
        detail = content_feature.detail
        return {
            "contentid": detail.contentid,
            "title": detail.title,
            "address": self._get_full_address(detail),
            "image": detail.firstimage or detail.firstimage2,
            "category": detail.lclsSystm3
        }

    def _get_full_address(self, detail):
        """주소 조합"""
        parts = []
        if detail.addr1 and detail.addr1.strip():
            parts.append(detail.addr1.strip())
        if detail.addr2 and detail.addr2.strip():
            parts.append(detail.addr2.strip())
        return " ".join(parts)


# --- 헬퍼 함수: detailIntro2 API 호출 및 정보 추출 ---
def _get_detail_intro_info(api_key, ca_bundle_path, content_id, content_type_id):
    """
    detailIntro2 API를 호출하여 contentTypeId에 따른 상세 정보를 추출합니다.
    Args:
        api_key (str): TourAPI 인증키
        ca_bundle_path (str): certifi CA 번들 경로
        content_id (str): 콘텐츠 ID
        content_type_id (int): 콘텐츠 타입 ID
    Returns:
        dict: { '한글 레이블': '값', ... } 형태의 추가 정보 딕셔너리
    """
    intro_details_result = {}
    detail_intro_api_url = "http://apis.data.go.kr/B551011/KorService2/detailIntro2"
    params = {
        'serviceKey': api_key,
        'MobileOS': 'ETC',
        'MobileApp': 'Sumteuyeo',
        'contentId': content_id,
        'contentTypeId': content_type_id,
        '_type': 'json'
    }

    try:
        print(f"Attempting to call detailIntro2 API for contentId: {content_id}, contentTypeId: {content_type_id}...")
        response = requests.get(detail_intro_api_url, params=params, timeout=5, verify=ca_bundle_path)
        response.raise_for_status()
        data = response.json()
        print(f"detailIntro2 API call successful for contentId: {content_id}.")

        if data['response']['header']['resultCode'] == '0000':
            items = data['response']['body'].get('items', {}).get('item', [])
            if items:
                item = items[0] if isinstance(items, list) and items else (items if isinstance(items, dict) else None)

                if item:
                    # API 응답 필드명과 사용자 요청 필드(한글 레이블) 매핑

                    field_mappings_by_type = {
                        12: {  # 관광지
                            '수용인원': item.get('accomcount'),
                            '유모차대여정보': item.get('chkbabycarriage'),
                            '애완동물동반가능정보': item.get('chkpet'),
                            '개장일': item.get('opendate'),
                            '주차시설': item.get('parking'),
                            '쉬는날': item.get('restdate'),
                            '이용시간': item.get('usetime')
                        },
                        14: {  # 문화시설
                            '수용인원': item.get('accomcountculture'),
                            '유모차대여정보': item.get('chkbabycarriageculture'),
                            '애완동물동반가능정보': item.get('chkpetculture'),
                            '주차시설': item.get('parkingculture'),
                            '이용요금': item.get('usefee'),
                            '이용시간': item.get('usetimeculture')
                        },
                        15: {  # 행사/공연/축제
                            '행사시작일': item.get('eventstartdate'),
                            '행사종료일': item.get('eventenddate'),
                            '공연시간': item.get('playtime'),
                            '이용요금': item.get('usetimefestival')
                        },
                        28: {  # 레포츠
                            '수용인원': item.get('accomcountleports'),
                            '유모차대여정보': item.get('chkbabycarriageleports'),
                            '애완동물동반가능정보': item.get('chkpetleports'),
                            '개장기간': item.get('openperiod'),
                            '주차시설': item.get('parkingleports'),
                            '쉬는날': item.get('restdateleports'),
                            '입장료': item.get('usefeeleports'),
                            '이용시간': item.get('usetimeleports')
                        },
                        32: {  # 숙박
                            '주차시설': item.get('parkinglodging')
                        },
                        38: {  # 쇼핑
                            '유모차대여정보': item.get('chkbabycarriageshopping'),
                            '애완동물동반가능정보': item.get('chkpetshopping'),
                            '영업시간': item.get('opentime'),
                            '주차시설': item.get('parkingshopping'),
                            '쉬는날': item.get('restdateshopping')
                        },
                        39: {  # 음식점
                            '대표메뉴': item.get('firstmenu'),
                            '어린이놀이방여부': item.get('kidsplayfacility'),
                            '주차시설': item.get('parkingfood'),
                            '쉬는날': item.get('restdatefood')
                        }
                    }

                    current_type_mappings = field_mappings_by_type.get(content_type_id, {})
                    for label, value in current_type_mappings.items():
                        if value and str(value).strip():  # 값이 존재하고 공백이 아닌 경우만 포함
                            intro_details_result[label] = str(value).strip()
        else:
            intro_error_msg = data['response']['header'].get('resultMsg', '소개 정보 API 오류')
            print(f"TourAPI Error (detailIntro2 for contentId {content_id}): {intro_error_msg}")

    except requests.exceptions.RequestException as e:
        print(f"Error calling detailIntro2 API for contentId {content_id}: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON from detailIntro2 for contentId {content_id}: {e}")
    except Exception as e:
        print(f"Unexpected error in _get_detail_intro_info for contentId {content_id}: {e}")

    return intro_details_result


# --- Helper Function: 주변 관광지 목록 가져오기 (Lazy Loading 적용) ---
def get_nearby_places_list(latitude, longitude, api_key):
    places_summary_list = []
    error_message = None
    try:
        ca_bundle_path = certifi.where()
    except Exception as e:
        print(f"Error getting certifi path: {e}")
        return [], "certifi CA 번들 경로를 찾는 중 오류가 발생했습니다."

    location_api_url = "https://apis.data.go.kr/B551011/KorService1/locationBasedList1"
    location_params = {
        'serviceKey': api_key, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'mapX': longitude, 'mapY': latitude, 'radius': 20000,
        'listYN': 'Y', 'arrange': 'E',
        'contentTypeId': 12,  # 기본적으로 관광지(12)를 검색하나, API는 다양한 타입을 반환할 수 있음
        'numOfRows': 20,
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
                addr1 = item.get('addr1', '')
                addr2 = item.get('addr2', '')
                address_parts = []
                if addr1 and addr1.strip():
                    address_parts.append(addr1.strip())
                if addr2 and addr2.strip():
                    address_parts.append(addr2.strip())
                full_address = " ".join(address_parts)

                places_summary_list.append({
                    'contentid': item.get('contentid'),
                    'title': item.get('title', '이름 없음'),
                    'addr': full_address,
                    'tel': item.get('tel', ''),
                    'firstimage': item.get('firstimage', ''),
                    'contenttypeid': item.get('contenttypeid')  # 상세 정보 조회 시 필요
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


# --- 새로운 뷰 함수: 특정 관광지의 상세 정보 가져오기 (detailCommon1 + detailIntro2) ---
@require_GET
def get_place_detail_view(request, content_id):
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

    overview = ''
    homepage_url = ''
    tel_number = ''
    content_type_id_str = None
    intro_data = {}

    # 1. detailCommon1 호출
    detail_common_api_url = "https://apis.data.go.kr/B551011/KorService1/detailCommon1"
    common_params = {
        'serviceKey': TOUR_API_KEY, 'MobileOS': 'ETC', 'MobileApp': 'Sumteuyeo',
        'contentId': content_id, '_type': 'json', 'defaultYN': 'Y',
        'firstImageYN': 'N', 'areacodeYN': 'N', 'catcodeYN': 'N',
        'addrinfoYN': 'N', 'mapinfoYN': 'N', 'overviewYN': 'Y'
    }
    response_common = None  # detailCommon1의 응답 객체용
    response_common_text = ''  # detailCommon1의 응답 텍스트용

    try:
        print(f"Attempting to call detailCommon1 API for contentId: {content_id} (with explicit verify path)...")
        response_common = requests.get(detail_common_api_url, params=common_params, timeout=5, verify=ca_bundle_path)
        response_common_text = response_common.text
        response_common.raise_for_status()
        api_data_common = response_common.json()

        if api_data_common['response']['header']['resultCode'] == '0000':
            items_common = api_data_common['response']['body'].get('items', {})
            item_common = items_common.get('item')
            if item_common and isinstance(item_common, list):
                item_common = item_common[0] if item_common else None

            if item_common and isinstance(item_common, dict):
                overview = item_common.get('overview', '')
                homepage_raw = item_common.get('homepage', '')
                tel_number = item_common.get('tel', '')
                content_type_id_str = item_common.get('contenttypeid')

                if homepage_raw:
                    match = re.search(r'href=[\'"]?([^\'" >]+)', homepage_raw, re.IGNORECASE)
                    if match:
                        homepage_url = match.group(1)
                    elif 'http' in homepage_raw and '<' not in homepage_raw:
                        url_match = re.search(r'(https?://[^\s<>"\'()]+)', homepage_raw)
                        if url_match:
                            homepage_url = url_match.group(1)
                        else:
                            homepage_url = homepage_raw.split()[0] if homepage_raw.split() else ''
                    else:
                        homepage_url = ''
            else:
                print(f"detailCommon1: No item found for contentId {content_id} or item format error.")
        else:
            common_error = api_data_common['response']['header'].get('resultMsg', '공통 정보 API 오류')
            print(f"TourAPI Error (detailCommon1 for contentId {content_id}): {common_error}")
            # detailCommon1 실패 시, contenttypeid를 알 수 없으므로 intro 정보는 못 가져옴.
            # 하지만 overview, tel 등 일부 정보는 실패 메시지와 함께 반환할 수도 있음.
            # 여기서는 일단 빈 값으로 두고 아래에서 intro 정보만 추가 시도.

    except requests.exceptions.SSLError as e:
        print(f"!!! SSLError occurred (detailCommon1 for contentId {content_id}): {e}")
        return JsonResponse({'status': 'error', 'message': 'SSL 인증서 검증 오류 (공통정보)'}, status=502)
    except requests.exceptions.Timeout:
        print(f"API 요청 시간 초과 (detailCommon1 for contentId {content_id})")
        return JsonResponse({'status': 'error', 'message': '공통 정보 요청 시간 초과'}, status=504)
    except requests.exceptions.RequestException as e:
        print(f"API 요청 오류 (detailCommon1 for contentId {content_id}): {e}")
        if response_common is not None: print(
            f"  Response Status Code (detailCommon1) was: {response_common.status_code}")
        return JsonResponse({'status': 'error', 'message': '공통 정보 요청 중 네트워크 오류'}, status=502)
    except json.JSONDecodeError:
        print(f"JSON Decode Error (detailCommon1 for contentId {content_id})")
        if response_common is not None: print(
            f"Received non-JSON response text (detailCommon1): {response_common_text[:200]}")
        return JsonResponse({'status': 'error', 'message': '공통 정보 API 응답 형식 오류'}, status=502)
    except Exception as e:  # detailCommon1 호출 또는 처리 중 기타 예외
        print(f"Unexpected error during detailCommon1 processing for contentId {content_id}: {e}")
        # 여기서 return JsonResponse를 하면 detailIntro2 호출 기회가 없음.
        # content_type_id_str이 None으로 유지되어 intro_data가 비게 됨. 이는 의도된 동작일 수 있음.

    # 2. contenttypeid가 있다면 detailIntro2 호출
    if content_type_id_str:
        try:
            content_type_id_int = int(content_type_id_str)
            intro_data = _get_detail_intro_info(TOUR_API_KEY, ca_bundle_path, content_id, content_type_id_int)
        except ValueError:
            print(f"Invalid contentTypeId format: {content_type_id_str} for contentId: {content_id}")
    else:
        print(
            f"Cannot fetch intro details because contentTypeId is missing for contentId: {content_id} (detailCommon1 might have failed or not provided it).")

    # 최종 응답 조합 (detailCommon1이 실패했더라도, 기본값들과 빈 intro_data로 응답 시도)
    return JsonResponse({
        'status': 'success',  # detailCommon1에서 오류가 나도 부분 성공으로 간주할지, 아니면 여기서도 error로 할지 결정 필요
        'contentid': content_id,
        'overview': overview,
        'tel': tel_number,
        'homepage': homepage_url,
        'intro_details': intro_data
    })


@ensure_csrf_cookie
def location_page_view(request):
    return render(request, 'core/main_page.html')


@require_POST
def receive_location(request):
    try:
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        if latitude is None or longitude is None:
            return JsonResponse({'status': 'error', 'message': '필수 파라미터(latitude, longitude)가 누락되었습니다.'}, status=400)

        try:
            TOUR_API_KEY = settings.TOUR_API_KEY
            if not TOUR_API_KEY: raise AttributeError("TOUR_API_KEY not found in settings")
        except AttributeError:
            error_msg = "settings.py에 TOUR_API_KEY가 정의되지 않았거나 비어있습니다."
            print(f"설정 오류: {error_msg}")
            return JsonResponse({'status': 'error', 'message': 'API 키 설정에 문제가 발생했습니다.'}, status=500)

        print("Calling get_nearby_places_list function...")
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
            return JsonResponse({'status': 'success', 'places': places_summary_list})

    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': '잘못된 요청 형식입니다.'}, status=400)
    except Exception as e:
        print(f"Unexpected error in receive_location view: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)
