from django.shortcuts import render

# Create your views here.
def main_page_view(request):
    return render(request, 'core/main_page.html')

def my_info_view(request):
    """'내 정보' 페이지를 렌더링합니다."""
    # 필요하다면 여기서 데이터베이스 조회 등 로직을 추가할 수 있습니다.
    return render(request, 'my-info.html')

def survey_view(request):
    """'설문조사' 페이지를 렌더링합니다."""
    return render(request, 'survey.html')

def mod_request_view(request):
    """'관광정보 수정요청' 페이지를 렌더링합니다."""
    # URL의 쿼리 파라미터에서 itemName 값을 가져옵니다. (예: /mod-request/?itemName=해운대해수욕장)
    item_name = request.GET.get('itemName', '') # 값이 없으면 빈 문자열
    
    # 가져온 값을 템플릿에 context로 전달하여, 수정 요청 페이지에서 활용할 수 있습니다.
    context = {
        'item_name': item_name
    }
    return render(request, 'mod-request.html', context)