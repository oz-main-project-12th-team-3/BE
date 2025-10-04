from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login

# from django.utils.decorators import method_decorator
# from django.views.decorators.csrf import csrf_exempt
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import JWTAuthentication
from ..exceptions import (
    PasswordMismatchException,
    TokenAuthenticationFailed,
)
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import (
    CheckEmailSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserRegisterSerializer,
)
from ..services.token_service import TokenService
from ..services.user_service import UserService


# @method_decorator(csrf_exempt, name="dispatch")
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
        serializer = UserRegisterSerializer(
            data=request.data, context={"user_service": user_service}
        )
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        nickname = serializer.validated_data.get("nickname")
        enable_2fa = serializer.validated_data.get("enable_2fa", False)

        try:
            user = user_service.create_user(email, password, nickname, enable_2fa)

            # 2FA 활성화 시 'setup' 단계로 분기
            if enable_2fa:
                # 1. 2FA 활성화 시: 임시 토큰 발급 및 2FA 설정 단계 강제
                access_token_to_set, refresh_token_to_set, access_token_lifetime = (
                    user_service.token_service.generate_temporary_tokens(user)
                )

                # E501 수정: 문자열을 괄호로 묶어 줄바꿈
                detail_message = (
                    "회원가입이 완료되었습니다. 2FA 설정을 "
                    "진행해야 완전한 로그인이 가능합니다."
                )
                response_data = {
                    "detail": detail_message,
                    "user_id": user.id,
                    "email": user.email,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                    "access_token": None,
                    "tfa_required": True,
                    "tfa_step": "setup",  # 2fa setup 단계
                    "temporary_access_token": access_token_to_set,
                    "temporary_refresh_token": refresh_token_to_set,
                }
            else:
                # 2. 2FA 비활성화 시: 정식 토큰 발급 (기존 로직)
                access_token_to_set, refresh_token_to_set, access_token_lifetime = (
                    user_service.token_service.generate_tokens(user)
                )

                response_data = {
                    "detail": "회원가입이 성공적으로 완료되었습니다.",
                    "user_id": user.id,
                    "email": user.email,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                    "access_token": access_token_to_set,
                    "tfa_required": False,
                    "tfa_step": "none",
                    "temporary_access_token": None,
                    "temporary_refresh_token": None,
                }

            # 쿠키 설정 로직 통일 (분기된 토큰 사용)
            response = Response(response_data, status=status.HTTP_201_CREATED)
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False

            # 토큰을 httponly, secure 쿠키에 저장하여 클라이언트에서 인증 유지
            response.set_cookie(
                "access_token",
                access_token_to_set,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(access_token_lifetime.total_seconds()),
            )
            response.set_cookie(
                "refresh_token",
                refresh_token_to_set,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )

            return response

        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        code = request.data.get("code")  # 2FA 코드가 있다면 사용

        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        user_service = UserService(
            user_repo, token_repo, token_service
        )  # ⭐ UserService 객체 생성

        # 1. UserService를 통해 로그인 인증 및 2FA 상태 판단/토큰 발급 로직 실행
        try:
            (
                user,
                login_success,  # 인증 성공 여부 (비밀번호, 잠금, 2FA 포함)
                tfa_required,  # 2FA 인증이 추가로 필요한지 여부
                tfa_step,
                temp_access_token,
                temp_refresh_token,
            ) = user_service.login_with_optional_2fa(email, password, code)
        except Exception as e:
            # authenticate_user 내에서 발생하는 오류 처리 (비번 불일치, 계정 잠금 등)
            detail_message = str(e) if str(e) else "로그인 정보가 올바르지 않습니다."
            return Response(
                {"detail": detail_message},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)  # Django 세션 로그인

        # 2. 2FA 필요 여부에 따라 응답 분기
        if tfa_required:
            # 2FA 등록 유저는 임시 토큰 발급 후 2FA 인증 단계로
            temp_lifetime = timedelta(
                minutes=5
            )  # 임시 토큰 만료 시간 (TokenService와 동일)
            response_data = {
                "detail": "2FA 인증이 필요합니다.",
                "user_id": user.id,
                "email": user.email,
                "expires_in": int(temp_lifetime.total_seconds()),
                "access_token": None,
                "tfa_required": True,
                "tfa_step": tfa_step,
                "temporary_access_token": temp_access_token,
                "temporary_refresh_token": temp_refresh_token,
            }

            response = Response(response_data, status=status.HTTP_200_OK)
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False

            response.set_cookie(
                "access_token",
                temp_access_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(temp_lifetime.total_seconds()),
            )
            response.set_cookie(
                "refresh_token",
                temp_refresh_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )
            return response

        # 3. 2FA 미등록 유저 또는 2FA 인증 완료 (정식 토큰 발급)
        # login_with_optional_2fa에서 2FA 인증까지 완료시 사용
        access_token, refresh_token, access_token_lifetime = (
            token_service.generate_tokens(user)
        )
        response_data = {
            "detail": "로그인 성공",
            "user_id": user.id,
            "email": user.email,
            "expires_in": int(access_token_lifetime.total_seconds()),
            "access_token": access_token,
            "tfa_required": False,
            "tfa_step": "none",
            "temporary_access_token": None,
            "temporary_refresh_token": None,
        }

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
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        )
        return response


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
        except PasswordMismatchException as e:
            detail_message = str(e) if str(e) else "비밀번호 불일치 오류"
            return Response(
                {"detail": detail_message}, status=status.HTTP_401_UNAUTHORIZED
            )
        except ValueError as e:  # 👈 이 부분을 추가하여 유효하지 않은 링크 오류 처리
            detail_message = (
                str(e) if str(e) else "유효하지 않은 비밀번호 재설정 링크입니다."
            )
            return Response(
                {"detail": detail_message}, status=status.HTTP_401_UNAUTHORIZED
            )
