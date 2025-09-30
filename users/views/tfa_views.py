import base64
from io import BytesIO

import qrcode
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import JWTAuthentication
from ..exceptions import UserNotFoundException
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import TwoFactorAuthSerializer
from ..services.token_service import TokenService
from ..services.user_service import UserService


class TwoFactorSetupView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def _generate_qr_code_base64(self, otp_uri):
        """OTP URI를 QR코드 이미지 base64 문자열로 변환"""
        qr = qrcode.make(otp_uri)
        buffered = BytesIO()
        qr.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str

    def post(self, request):
        user_service = self._get_user_service()
        user = request.user
        try:
            device = user_service.setup_2fa(user)
        except Exception as e:
            return Response(
                {"detail": f"2FA 설정 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        otp_uri = device.config_url
        qr_code_base64 = self._generate_qr_code_base64(otp_uri) if otp_uri else None

        if device.confirmed:
            return Response(
                {
                    "detail": "2FA 기기가 이미 등록되어 있습니다.",
                    "device_id": device.id,
                    "otp_uri": otp_uri,
                    "qr_code_base64": qr_code_base64,
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {
                    "detail": "2FA 기기가 등록되었습니다.",
                    "device_id": device.id,
                    "otp_uri": otp_uri,
                    "qr_code_base64": qr_code_base64,
                },
                status=status.HTTP_201_CREATED,
            )


class TwoFactorConfirmView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
        user = request.user
        code = request.data.get("code")

        if not code:
            return Response(
                {"detail": "인증 코드가 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            confirmed = user_service.confirm_2fa(user, code)
            if confirmed:
                return Response({"detail": "2FA 등록이 완료되었습니다."})
            else:
                return Response(
                    {"detail": "잘못된 인증 코드"}, status=status.HTTP_400_BAD_REQUEST
                )
        except Exception as e:
            return Response(
                {"detail": f"2FA 등록 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwoFactorVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_services(self):
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        user_service = UserService(user_repo, token_repo, token_service)
        return user_service, token_service

    def post(self, request):
        user_service, token_service = self._get_services()

        serializer = TwoFactorAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = request.data.get("email")
        code = serializer.validated_data["code"]

        if not email:
            return Response(
                {"detail": "이메일이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = user_service.verify_2fa(email, code)

            access_token, refresh_token, access_token_lifetime = (
                token_service.generate_tokens(user)
            )
            response = Response(
                {
                    "detail": "2FA 인증 성공",
                    "user_id": user.id,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                    "access_token": access_token,
                },
                status=status.HTTP_200_OK,
            )

            # 보안 쿠키 설정
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

        except (UserNotFoundException, ValueError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"detail": f"2FA 인증 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TwoFactorLoginView(APIView):
    """
    django-two-factor-auth의 내장 로그인 뷰를 사용하므로 API에서 별도 구현 X
    """

    pass
