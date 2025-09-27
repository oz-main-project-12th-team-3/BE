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

# ⚠️ 전역 객체 선언은 삭제되었습니다. (CI/테스트 환경 문제 해결)
# user_repo = UserRepository()
# token_repo = TokenRepository()
# token_service = TokenService(user_repo, token_repo)
# user_service = UserService(user_repo, token_repo, token_service)


class TwoFactorSetupView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        """서비스 객체를 생성하여 반환합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
        user = request.user
        device = user_service.setup_2fa(user)

        otp_uri = device.config_url
        qr_code_base64 = None  # 프론트에서 otp_uri로 QR 코드 생성 권장

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
        """서비스 객체를 생성하여 반환합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
        user = request.user
        code = request.data.get("code")

        if user_service.confirm_2fa(user, code):
            return Response({"detail": "2FA 등록이 완료되었습니다."})
        return Response(
            {"detail": "잘못된 인증 코드"}, status=status.HTTP_400_BAD_REQUEST
        )


class TwoFactorVerifyView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_services(self):
        """서비스 및 레포지토리 객체들을 생성하여 반환합니다."""
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

            # 쿠키 설정 로직
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False
            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(access_token_lifetime.total_seconds()),
            )
            response.set_cookie(
                "refresh_token",
                refresh_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )
            return response

        except (UserNotFoundException, ValueError) as e:
            # 2FA 장치 없음 오류도 ValueError로 처리되어 detail에 담깁니다.
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"detail": f"2FA 인증 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
