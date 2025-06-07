import json

from django.http import JsonResponse
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm # Django 기본 로그인 폼
from django.views.decorators.http import require_POST # POST 요청만 허용하는 데코레이터
from django.views.decorators.http import require_GET # GET 요청만 허용
from django.db import IntegrityError # 데이터베이스 레벨 오류 처리용
from django.db.models import Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from datetime import datetime
from django.db.models import Prefetch
from apps.recommender.services.theme_recommender import ThemeRecommender
from apps.items.models import ContentDetailCommon
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers

# 회원가입 폼 (forms.Form 상속 버전)
from .forms import UserSignupAPIForm

User = get_user_model() # 현재 활성화된 사용자 모델 가져오기

@require_POST # POST 요청만 허용
def signup_api_view(request):
    """회원가입 API 뷰"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': '잘못된 JSON 형식입니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )

    form = UserSignupAPIForm(data) # 일반 Form 기반의 회원가입 폼 사용
    if form.is_valid():
        # 폼 유효성 검사 통과
        username = form.cleaned_data['username']
        password = form.cleaned_data['password_1'] # password_1 필드 값 사용
        email = form.cleaned_data['email']

        try:
            # User.objects.create_user() 사용하여 사용자 생성 (비밀번호 자동 해싱)
            user = User.objects.create_user(username=username, password=password, email=email)
            # 회원가입 후 바로 로그인 처리
            login(request, user)
            return JsonResponse(
                {
                    'status': 'success',
                    'message': '회원가입이 완료되었습니다. 자동으로 로그인됩니다.',
                    'username': user.username
                },
                json_dumps_params={'ensure_ascii': False} # 한글 처리
            )
        except IntegrityError: # DB 레벨 중복 오류 (폼에서 이미 걸렀다면 발생 확률 낮음)
            return JsonResponse(
                {'status': 'error', 'message': '사용자 생성 중 오류가 발생했습니다. (DB 오류)'},
                status=400,
                json_dumps_params={'ensure_ascii': False} # 한글 처리
            )
        except Exception as e: # 기타 예상 못한 오류
             return JsonResponse(
                {'status': 'error', 'message': '사용자 처리 중 내부 오류가 발생했습니다.'},
                status=500,
                json_dumps_params={'ensure_ascii': False} # 한글 처리
            )
    else:
        # 폼 유효성 검사 실패
        return JsonResponse(
            {'status': 'error', 'errors': form.errors.get_json_data()},
            status=400,
            json_dumps_params={'ensure_ascii': False} # 폼 에러 메시지에 한글이 있을 수 있음
        )

@require_POST # POST 요청만 허용
def login_api_view(request):
    """로그인 API 뷰"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': '잘못된 JSON 형식입니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )

    # Django 기본 AuthenticationForm 사용 (request 객체 필수 전달)
    form = AuthenticationForm(request, data=data)
    if form.is_valid():
        # 폼 유효성 검사 통과 (사용자 인증 성공)
        user = form.get_user()
        login(request, user) # Django의 login 함수로 세션 생성
        return JsonResponse(
            {
                'status': 'success',
                'message': '로그인 성공!',
                'username': user.username
            },
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )
    else:
        # 폼 유효성 검사 실패 (인증 실패)
        return JsonResponse(
            {'status': 'error', 'message': '아이디 또는 비밀번호가 올바르지 않습니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )

@require_POST # POST 요청만 허용
def logout_api_view(request):
    """로그아웃 API 뷰"""
    if request.user.is_authenticated: # 로그인 상태 확인
        logout(request) # Django의 logout 함수로 세션에서 사용자 제거
        return JsonResponse(
            {'status': 'success', 'message': '로그아웃 되었습니다.'},
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )
    else:
        # 비로그인 상태에서 로그아웃 요청 시
        return JsonResponse(
            {'status': 'error', 'message': '로그인 상태가 아닙니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False} # 한글 처리
        )

@require_GET # GET 요청만 허용
def check_auth_status(request):
    """현재 사용자의 인증 상태를 확인하는 API 뷰"""
    if request.user.is_authenticated:
        # 로그인 상태일 경우
        return JsonResponse({
            'isAuthenticated': True,
            'username': request.user.username # 사용자 이름 추가
        }, json_dumps_params={'ensure_ascii': False})
    else:
        # 로그아웃 상태일 경우
        return JsonResponse({'isAuthenticated': False})

class BookmarkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_ids = request.user.bookmarks.values_list('content_id', flat=True)
        bookmarks = ContentDetailCommon.objects.filter(contentid__in=content_ids)

        # 직렬화
        serializer = SimpleBookmarkSerializer(bookmarks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class SimpleBookmarkSerializer(serializers.ModelSerializer):
    address = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    
    class Meta:
        model = ContentDetailCommon
        fields = ['contentid', 'title', 'address', 'image', 'lclsSystm3']
        read_only_fields = fields

    def get_address(self, obj):
        return " ".join(filter(None, [obj.addr1.strip() if obj.addr1 else None, 
                                    obj.addr2.strip() if obj.addr2 else None]))

    def get_image(self, obj):
        return obj.firstimage or obj.firstimage2
