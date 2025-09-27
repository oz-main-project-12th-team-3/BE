from django.conf import settings
from rest_framework import permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import JWTAuthentication
from ..exceptions import (
    PasswordMismatchException,
    TokenAuthenticationFailed,
    UserNotFoundException,
)
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import (
    CheckEmailSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserLoginSerializer,
    UserRegisterSerializer,
)
from ..services.token_service import TokenService
from ..services.user_service import UserService

# ⚠️ 전역 객체 선언 제거:
# user_repo = UserRepository()
# token_repo = TokenRepository()
# token_service = TokenService(user_repo, token_repo)
# user_service = UserService(user_repo, token_repo, token_service)


class UserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request, *args, **kwargs):
        user_service = self._get_user_service()
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        nickname = serializer.validated_data.get("nickname")
        enable_2fa = serializer.validated_data.get("enable_2fa", False)

        try:
            user = user_service.create_user(email, password, nickname, enable_2fa)
            response_data = {
                "detail": "회원가입이 성공적으로 완료되었습니다.",
                "user_id": user.id,
                "email": user.email,
                "2fa_setup_required": enable_2fa,
            }
            return Response(response_data, status=status.HTTP_201_CREATED)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_services(self):
        """요청 시마다 독립적인 서비스 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        user_service = UserService(user_repo, token_repo, token_service)
        return user_service, token_service

    def post(self, request):
        user_service, token_service = self._get_services()
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        code = request.data.get("tfa_code")  # 2FA 코드 선택적

        try:
            user, verified, is_temp_token, *tokens = (
                user_service.login_with_optional_2fa(email, password, code)
            )

            response_data = {
                "detail": None,
                "user_id": None,
                "email": None,
                "expires_in": None,
                "access_token": None,
                "refresh_token": None,
                "tfa_required": False,
                "tfa_step": "none",
                "temporary_access_token": None,
                "temporary_refresh_token": None,
            }

            if is_temp_token:
                temp_access_token, temp_refresh_token = tokens
                response_data.update(
                    {
                        "detail": "2FA 설정이 필요합니다.",
                        "tfa_required": True,
                        "tfa_step": "setup",
                        "temporary_access_token": temp_access_token,
                        "temporary_refresh_token": temp_refresh_token,
                    }
                )
                return Response(response_data, status=status.HTTP_200_OK)

            if not verified:
                response_data.update(
                    {
                        "detail": "2FA 인증 코드가 필요합니다.",
                        "tfa_required": True,
                        "tfa_step": "verify",
                        "user_id": user.id,
                    }
                )
                return Response(response_data, status=status.HTTP_200_OK)

            access_token, refresh_token, access_token_lifetime = (
                token_service.generate_tokens(user)
            )

            response_data.update(
                {
                    "detail": "로그인 성공",
                    "user_id": user.id,
                    "email": user.email,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "tfa_required": False,
                    "tfa_step": "none",
                }
            )

            response = Response(response_data, status=status.HTTP_200_OK)

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

        except (UserNotFoundException, PasswordMismatchException) as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_token_repo(self):
        """요청 시마다 독립적인 TokenRepository 객체를 생성합니다."""
        return TokenRepository()

    def post(self, request):
        token_repo = self._get_token_repo()
        if request.user:
            token_repo.blacklist_all_user_tokens(request.user)

        response = Response(
            {"detail": "로그아웃 되었습니다."}, status=status.HTTP_200_OK
        )
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class TokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_token_service(self):
        """요청 시마다 독립적인 TokenService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        return TokenService(user_repo, token_repo)

    def post(self, request):
        token_service = self._get_token_service()
        refresh_token = (
            request.COOKIES.get("refresh_token")
            or request.data.get("refresh_token")
            or request.data.get("refresh")
        )

        try:
            access_token, new_refresh_token, access_token_lifetime, user = (
                token_service.refresh_user_tokens(refresh_token)
            )

            response = Response(
                {
                    "detail": "토큰이 성공적으로 갱신되었습니다.",
                    "access_token": access_token,
                    "user_id": user.id,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                },
                status=status.HTTP_200_OK,
            )
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
                new_refresh_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )
            return response

        except TokenAuthenticationFailed as e:
            response = Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            return response
        except Exception as e:
            return Response(
                {"detail": f"토큰 갱신 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
        serializer = CheckEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")

        is_available = not user_service.check_email_exists(email)
        message = (
            "사용 가능한 이메일입니다."
            if is_available
            else "이미 사용중인 이메일입니다."
        )

        return Response(
            {"available": is_available, "detail": message}, status=status.HTTP_200_OK
        )


class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        domain = request.get_host()
        protocol = "https" if request.is_secure() else "http"
        user_service.send_password_reset_email(email, domain, protocol)
        return Response(
            {"detail": "비밀번호 재설정 메일이 발송되었습니다."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    permission_classes = [permissions.AllowAny]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request, uidb64, token):
        user_service = self._get_user_service()
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_password = serializer.validated_data["new_password"]

        try:
            user_service.reset_password(uidb64, token, new_password)
            return Response(
                {"detail": "비밀번호가 성공적으로 재설정되었습니다."},
                status=status.HTTP_200_OK,
            )
        except ValueError as e:
            raise ValidationError({"detail": str(e)})