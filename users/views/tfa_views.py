import base64
from io import BytesIO

import qrcode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.redis_client import get_redis_client

from ..authentication import JWTAuthentication, TemporaryJWTAuthentication
from ..exceptions import TfaVerificationFailedException
from ..repositories.login_fail_lock_repository import LoginFailLockRepository
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import TfaSetupConfirmSerializer, TfaVerifySerializer
from ..services.token_service import TokenService
from ..services.user_service import UserService


class BaseTfaView(APIView):
    """2FA 뷰를 위한 공통 로직 및 서비스 의존성 관리"""

    def _get_services(self):
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        redis_client = get_redis_client()
        redis_repo = LoginFailLockRepository(redis_client=redis_client)
        user_service = UserService(user_repo, token_repo, token_service, redis_repo)
        return user_service, token_service

    def _generate_qr_code_base64(self, otp_uri):
        """OTP URI를 QR코드 이미지 base64 문자열로 변환"""
        qr = qrcode.make(otp_uri)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str

    def _set_auth_cookies(
        self, response, access_token, refresh_token, access_token_lifetime
    ):
        """JWT 토큰을 쿠키에 설정합니다."""
        secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False
        max_age_access = int(access_token_lifetime.total_seconds())
        max_age_refresh = int(
            settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
        )

        response.set_cookie(
            "access_token",
            access_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",
            max_age=max_age_access,
        )
        response.set_cookie(
            "refresh_token",
            refresh_token,
            httponly=True,
            secure=secure_cookie,
            samesite="Strict",
            max_age=max_age_refresh,
        )
        return response


@extend_schema(
    responses={
        200: OpenApiResponse(description="2FA 내장 페이지로 리다이렉트"),
        403: OpenApiResponse(description="접근 권한 없음 또는 2FA 필요 없음"),
    },
    summary="2FA 내장 페이지 리다이렉트",
    description="2FA 상태에 따라 django-two-factor-auth 내장 페이지로 리다이렉트",
)
class TwoFactorWrapperView(APIView):
    """
    📌 옵션 2: Django-two-factor-auth 내장 페이지로 리다이렉트

    UserLoginView에서 임시 토큰 발급 후 이 뷰의 URL로 리다이렉트.
    이 뷰는 세션의 'tfa_step'을 확인하여 내장 뷰(setup 또는 login)로 최종 리다이렉트.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        tfa_step = request.session.get("tfa_step", "none")

        if request.user.is_authenticated:
            if tfa_step == "setup":
                return redirect(reverse("two_factor:setup"))

            if tfa_step == "verify":
                return redirect(reverse("two_factor:login"))

        return Response(
            {"detail": "접근 권한이 없거나 2FA 처리가 필요하지 않습니다."},
            status=status.HTTP_403_FORBIDDEN,
        )


class TfaApiView(BaseTfaView):
    """
    📌 옵션 1: 커스텀 2FA 페이지를 위한 API (단일 엔드포인트)

    임시 JWT 토큰으로 인증하고, 2FA 성공 시 정식 JWT 토큰을 발급.
    """

    authentication_classes = [TemporaryJWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(
                description="2FA 설정 정보와 QR 코드 base64 문자열 반환"
            ),
            403: OpenApiResponse(description="2FA 설정 불가 단계"),
            500: OpenApiResponse(description="서버 내부 오류"),
        },
        summary="2FA 설정 정보 조회 (GET)",
        description="2FA 설정 단계에서 QR 코드 생성 및 반환",
    )
    def get(self, request):
        user_service, _ = self._get_services()
        user = request.user
        tfa_step = request.session.get("tfa_step", "none")

        if tfa_step != "setup":
            return Response(
                {"detail": "2FA 설정을 시작할 수 있는 단계가 아닙니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            device = user_service.setup_2fa(user)
            otp_uri = device.config_url
            qr_code_base64 = self._generate_qr_code_base64(otp_uri) if otp_uri else None

            return Response(
                {
                    "detail": "2FA 설정을 위한 정보가 발급되었습니다.",
                    "otp_uri": otp_uri,
                    "qr_code_base64": qr_code_base64,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"detail": f"2FA 설정 정보 발급 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        request={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "2FA 인증 코드"}},
            "required": ["code"],
        },
        responses={
            200: OpenApiResponse(description="2FA 인증 성공 및 토큰 발급"),
            400: OpenApiResponse(description="잘못된 2FA 처리 단계"),
            401: OpenApiResponse(description="2FA 인증 실패"),
            500: OpenApiResponse(description="서버 내부 오류"),
        },
        summary="2FA 인증 및 설정 완료 (POST)",
        description="2FA 인증 코드 검증 및 인증 성공 시 JWT 토큰 발급",
    )
    def post(self, request):
        user_service, token_service = self._get_services()
        user = request.user
        tfa_step = request.session.get("tfa_step", "none")

        if tfa_step == "setup":
            serializer = TfaSetupConfirmSerializer(data=request.data)
            confirm_method = user_service.confirm_2fa
            success_detail = "2FA 설정이 완료되었습니다."

        elif tfa_step == "verify":
            serializer = TfaVerifySerializer(data=request.data)
            confirm_method = user_service.verify_2fa_by_user
            success_detail = "2FA 인증에 성공했습니다."

        else:
            return Response(
                {"detail": "잘못된 2FA 처리 단계입니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data["code"]

        try:
            confirmed = confirm_method(user, code)

            if not confirmed:
                raise TfaVerificationFailedException("잘못된 인증 코드")

            if "tfa_step" in request.session:
                del request.session["tfa_step"]

            access_token, refresh_token, access_token_lifetime = (
                token_service.generate_tokens(user)
            )

            response = Response(
                {
                    "detail": success_detail,
                    "tfa_required": False,
                    "tfa_step": "none",
                    "expires_in": int(access_token_lifetime.total_seconds()),
                    "access_token": access_token,
                },
                status=status.HTTP_200_OK,
            )

            return self._set_auth_cookies(
                response, access_token, refresh_token, access_token_lifetime
            )

        except TfaVerificationFailedException as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response(
                {"detail": f"2FA 처리 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwoFactorDisableView(BaseTfaView):
    """
    2FA 설정을 해제하는 뷰. (정식 JWT 토큰으로 인증)
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="2FA 해제 성공"),
            500: OpenApiResponse(description="서버 오류"),
        },
        summary="2FA 비활성화",
        description="사용자의 2FA 설정을 해제",
    )
    def delete(self, request):
        user_service, _ = self._get_services()
        user = request.user

        try:
            user_service.disable_2fa(user)
            return Response(
                {"detail": "2FA가 성공적으로 해제되었습니다."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            return Response(
                {"detail": f"2FA 해제 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
