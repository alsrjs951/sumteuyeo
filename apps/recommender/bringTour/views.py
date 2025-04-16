import json
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie # CSRF 쿠키 설정을 위해 필요할 수 있음
from django.views.decorators.http import require_POST # POST 요청만 받도록 설정
from django.shortcuts import render # HTML 템플릿 렌더링을 위해

# HTML 페이지를 보여주는 뷰 (프론트엔드 코드가 담긴 템플릿)
@ensure_csrf_cookie # 이 뷰가 렌더링될 때 CSRF 쿠키를 설정하도록 보장
def location_page_view(request):
    # 위에서 작성한 HTML 파일 이름을 적절히 지정하세요. (예: 'location_page.html')
    return render(request, 'yourapp/location_page.html') # templates/yourapp/location_page.html 경로

# 프론트엔드로부터 위치 정보를 받는 API 뷰
@require_POST # 이 뷰는 POST 요청만 허용
def receive_location(request):
    try:
        # 요청 본문(body)에서 JSON 데이터를 파싱합니다.
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')

        # 위도, 경도 값이 제대로 들어왔는지 확인
        if latitude is None or longitude is None:
            return HttpResponseBadRequest("필수 파라미터(latitude, longitude)가 누락되었습니다.")

        # 여기에 전달받은 위도(latitude), 경도(longitude)를 사용하는 로직을 추가합니다.
        # 예시: 콘솔에 출력
        print(f"수신된 위치: 위도={latitude}, 경도={longitude}")

        # TODO: 이 위치 정보를 기반으로 주변 관광지/축제 API를 호출하고 결과를 처리하는 로직 구현

        # 성공적으로 처리되었음을 프론트엔드에 알리는 JSON 응답
        return JsonResponse({'status': 'success', 'message': '위치 정보를 성공적으로 받았습니다.'})

    except json.JSONDecodeError:
        return HttpResponseBadRequest("잘못된 JSON 형식입니다.")
    except Exception as e:
        # 기타 예상치 못한 오류 처리
        print(f"오류 발생: {e}")
        return JsonResponse({'status': 'error', 'message': '서버 처리 중 오류가 발생했습니다.'}, status=500)