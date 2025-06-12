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
                content_id = item.contentid
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

    def _serialize_content(self, detail):
        """개별 콘텐츠 직렬화"""
        return {
            "contentid": detail.contentid,
            "title": detail.title,
            "address": self._get_full_address(detail),
            "image": detail.firstimage or detail.firstimage2,
            "category": detail.lclssystm3
        }

    def _get_full_address(self, detail):
        """주소 조합"""
        parts = []
        if detail.addr1 and detail.addr1.strip():
            parts.append(detail.addr1.strip())
        if detail.addr2 and detail.addr2.strip():
            parts.append(detail.addr2.strip())
        return " ".join(parts)
