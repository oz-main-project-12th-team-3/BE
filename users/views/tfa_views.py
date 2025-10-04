import base64
from io import BytesIO

import qrcode
from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import JWTAuthentication, TemporaryJWTAuthentication
from ..exceptions import TfaVerificationFailedException
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
        user_service = UserService(user_repo, token_repo, token_service)
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


class TwoFactorWrapperView(APIView):
    """
    📌 옵션 2: Django-two-factor-auth 내장 페이지로 리다이렉트

    UserLoginView에서 임시 토큰 발급 후 이 뷰의 URL로 리다이렉트.
    이 뷰는 세션의 'tfa_step'을 확인하여 내장 뷰(setup 또는 login)로 최종 리다이렉트.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # 세션에서 2FA 단계 상태 호출
        tfa_step = request.session.get("tfa_step", "none")

        if request.user.is_authenticated:
            if tfa_step == "setup":
                return redirect(reverse("two_factor:setup"))

            if tfa_step == "verify":
                # 내장 뷰는 세션 인증 후 'two_factor:login'으로 자동 이동.
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

    # 1. GET: 2FA 설정(setup)을 위한 QR 코드 URI 요청
    def get(self, request):
        """
        tfa_step='setup' 단계일 때만 호출 가능.
        QR 코드 URI와 base64 이미지를 반환합니다.
        """
        user_service, _ = self._get_services()
        user = request.user
        tfa_step = request.session.get("tfa_step", "none")

        if not tfa_step == "setup":
            return Response(
                {"detail": "2FA 설정을 시작할 수 있는 단계가 아닙니다."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            # UserService의 setup_2fa 메서드 사용 (TOTPDevice 생성)
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

    # 2. POST: 2FA 설정 완료(Confirm) 또는 2FA 인증(Verify) 처리
    def post(self, request):
        """
        tfa_step에 따라 인증을 처리하고, 성공 시 정식 JWT 토큰을 발급합니다.
        """
        user_service, token_service = self._get_services()
        user = request.user
        tfa_step = request.session.get("tfa_step", "none")

        if tfa_step == "setup":
            # 2FA 설정 완료 (기존 TwoFactorConfirmView 로직 통합)
            serializer = TfaSetupConfirmSerializer(data=request.data)
            confirm_method = user_service.confirm_2fa
            success_detail = "2FA 설정이 완료되었습니다."

        elif tfa_step == "verify":
            # 2FA 로그인 인증 (기존 TwoFactorVerifyView 로직 통합)
            serializer = TfaVerifySerializer(data=request.data)
            # UserService에 verify_2fa_by_user(user, code) 메서드 필요.
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

            # 2FA 성공 후: 세션 상태 제거
            if "tfa_step" in request.session:
                del request.session["tfa_step"]

            # 정식 JWT 토큰 발급 및 쿠키 설정
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

    def delete(self, request):
        """사용자의 모든 TOTPDevice를 삭제하여 2FA를 비활성화합니다."""
        user_service, _ = self._get_services()
        user = request.user

        try:
            # 🚨 UserService에 disable_2fa(user) 메서드가 필요합니다.
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
