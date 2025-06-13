import json

from django.http import JsonResponse
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm  # Django 기본 로그인 폼
from django.views.decorators.http import require_POST  # POST 요청만 허용하는 데코레이터
from django.views.decorators.http import require_GET  # GET 요청만 허용
from django.db import IntegrityError  # 데이터베이스 레벨 오류 처리용
from django.db.models import Subquery
from rest_framework.views import APIView
from rest_framework.response import Response
from datetime import datetime
from django.db.models import Prefetch
from apps.recommender.services.theme_recommender import ThemeRecommender
from apps.items.models import ContentDetailCommon
from rest_framework.permissions import IsAuthenticated
from rest_framework import serializers, generics, permissions, status
from .models import UserRating
from .forms import UserSignupAPIForm
from rest_framework.exceptions import NotFound

# JWT 토큰 생성을 위한 RefreshToken 임포트
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()  # 현재 활성화된 사용자 모델 가져오기


@require_POST  # POST 요청만 허용
def signup_api_view(request):
    """회원가입 API 뷰"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': '잘못된 JSON 형식입니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False}  # 한글 처리
        )

    form = UserSignupAPIForm(data)  # 일반 Form 기반의 회원가입 폼 사용
    if form.is_valid():
        username = form.cleaned_data['username']
        password = form.cleaned_data['password_1']  # password_1 필드 값 사용
        email = form.cleaned_data['email']

        try:
            user = User.objects.create_user(username=username, password=password, email=email)
            login(request, user)

            # 회원가입 성공 시에도 토큰을 발급하여 바로 로그인된 상태를 유지합니다.
            refresh = RefreshToken.for_user(user)
            return JsonResponse(
                {
                    'status': 'success',
                    'message': '회원가입이 완료되었습니다. 자동으로 로그인됩니다.',
                    'username': user.username,
                    'access_token': str(refresh.access_token),
                    'refresh_token': str(refresh),
                },
                json_dumps_params={'ensure_ascii': False}
            )
        except IntegrityError:
            return JsonResponse(
                {'status': 'error', 'message': '사용자 생성 중 오류가 발생했습니다. (DB 오류)'},
                status=400,
                json_dumps_params={'ensure_ascii': False}
            )
        except Exception as e:
            return JsonResponse(
                {'status': 'error', 'message': '사용자 처리 중 내부 오류가 발생했습니다.'},
                status=500,
                json_dumps_params={'ensure_ascii': False}
            )
    else:
        return JsonResponse(
            {'status': 'error', 'errors': form.errors.get_json_data()},
            status=400,
            json_dumps_params={'ensure_ascii': False}
        )


@require_POST  # POST 요청만 허용
def login_api_view(request):
    """로그인 API 뷰 (수정됨)"""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {'status': 'error', 'message': '잘못된 JSON 형식입니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False}
        )

    form = AuthenticationForm(request, data=data)
    if form.is_valid():
        user = form.get_user()
        login(request, user)  # Django의 login 함수로 세션 생성

        # 로그인 성공 시, 해당 유저에 대한 JWT 토큰 생성
        refresh = RefreshToken.for_user(user)

        # 응답에 access_token과 refresh_token 추가
        return JsonResponse(
            {
                'status': 'success',
                'message': '로그인 성공!',
                'username': user.username,
                'access_token': str(refresh.access_token),
                'refresh_token': str(refresh),
            },
            json_dumps_params={'ensure_ascii': False}
        )
    else:
        return JsonResponse(
            {'status': 'error', 'message': '아이디 또는 비밀번호가 올바르지 않습니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False}
        )


@require_POST
def logout_api_view(request):
    """로그아웃 API 뷰"""
    if request.user.is_authenticated:
        logout(request)
        return JsonResponse(
            {'status': 'success', 'message': '로그아웃 되었습니다.'},
            json_dumps_params={'ensure_ascii': False}
        )
    else:
        return JsonResponse(
            {'status': 'error', 'message': '로그인 상태가 아닙니다.'},
            status=400,
            json_dumps_params={'ensure_ascii': False}
        )


@require_GET
def check_auth_status(request):
    """현재 사용자의 인증 상태를 확인하는 API 뷰"""
    if request.user.is_authenticated:
        return JsonResponse({
            'isAuthenticated': True,
            'username': request.user.username
        }, json_dumps_params={'ensure_ascii': False})
    else:
        return JsonResponse({'isAuthenticated': False})


class BookmarkListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        content_ids = request.user.bookmarks.values_list('content_id', flat=True)
        bookmarks = ContentDetailCommon.objects.filter(contentid__in=content_ids)
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


class UserRatingSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserRating
        fields = ['id', 'user', 'content', 'rating_type', 'created_at']


class UserRatingByContentView(generics.RetrieveAPIView):
    serializer_class = UserRatingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        content_id = self.kwargs['content_id']
        try:
            return UserRating.objects.get(
                user=self.request.user,  # 현재 인증된 사용자
                content_id=content_id  # URL 파라미터로 전달된 content_id
            )
        except UserRating.DoesNotExist:
            raise NotFound("해당 콘텐츠에 대한 평가 정보가 없습니다.")