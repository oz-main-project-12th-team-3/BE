from datetime import timedelta

from django.conf import settings
from django.contrib.auth import login
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.redis_client import get_redis_client

from ..authentication import JWTAuthentication
from ..exceptions import PasswordMismatchException, TokenAuthenticationFailed
from ..repositories.redis_lock_repository import RedisLockRepository
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import (
    CheckEmailSerializer,
    LoginResponseSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    UserLoginSerializer,
    UserRegisterSerializer,
)
from ..services.token_service import TokenService
from ..services.user_service import UserService


class UserRegisterView(APIView):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        redis_client = get_redis_client()
        redis_repo = RedisLockRepository(redis_client=redis_client)
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service, redis_repo)

    @extend_schema(
        request=UserRegisterSerializer,
        responses={201: UserRegisterSerializer},
        summary="유저 회원가입",
        description=(
            "이메일, 비밀번호, 닉네임, 2FA 활성화 여부를 받아 회원가입을 진행합니다."
        ),
    )
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

    def _get_services(self):
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        redis_client = get_redis_client()
        redis_repo = RedisLockRepository(redis_client=redis_client)
        user_service = UserService(user_repo, token_repo, token_service, redis_repo)
        return user_service, token_service

    @extend_schema(
        request=UserLoginSerializer,
        responses={200: LoginResponseSerializer, 401: LoginResponseSerializer},
        summary="유저 로그인",
        description=(
            "이메일, 비밀번호, 선택적 2FA 코드로 로그인, "
            "결과에 따라 2FA 필요 여부 및 토큰 반환"
        ),
    )
    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        code = serializer.validated_data.get("tfa_code") or ""

        user_service, token_service = self._get_services()

        try:
            (
                user,
                login_success,
                tfa_required,
                tfa_step,
                temp_access_token,
                temp_refresh_token,
            ) = user_service.login_with_optional_2fa(email, password, code)
        except Exception as e:
            detail_message = str(e) or "로그인 정보가 올바르지 않습니다."
            response_data = {
                "detail": detail_message,
                "user_id": None,
                "email": None,
                "expires_in": 0,
                "access_token": None,
                "tfa_required": False,
                "tfa_step": "none",
                "temporary_access_token": None,
                "temporary_refresh_token": None,
                "profile_image_url": None,
            }
            return Response(response_data, status=status.HTTP_401_UNAUTHORIZED)

        login(request, user)  # Django 세션 로그인

        profile_image_url = (
            getattr(user.profile, "profile_image_url", None)
            if hasattr(user, "profile")
            else None
        )

        if tfa_required:
            temp_lifetime = timedelta(minutes=5)
            expires_in = int(temp_lifetime.total_seconds())
            response_data = {
                "detail": "2FA 인증이 필요합니다.",
                "user_id": user.id,
                "email": user.email,
                "expires_in": expires_in,
                "access_token": None,
                "tfa_required": True,
                "tfa_step": tfa_step,
                "temporary_access_token": temp_access_token,
                "temporary_refresh_token": temp_refresh_token,
                "profile_image_url": profile_image_url,
            }

            serializer = LoginResponseSerializer(data=response_data)
            serializer.is_valid(raise_exception=True)
            response = Response(serializer.validated_data, status=status.HTTP_200_OK)
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False

            response.set_cookie(
                "access_token",
                temp_access_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=expires_in,
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

        else:
            (
                access_token,
                refresh_token,
                access_token_lifetime,
            ) = token_service.generate_tokens(user)
            expires_in = int(access_token_lifetime.total_seconds())
            response_data = {
                "detail": "로그인 성공",
                "user_id": user.id,
                "email": user.email,
                "expires_in": expires_in,
                "access_token": access_token,
                "tfa_required": False,
                "tfa_step": "none",
                "temporary_access_token": None,
                "temporary_refresh_token": None,
                "profile_image_url": profile_image_url,
            }

            serializer = LoginResponseSerializer(data=response_data)
            serializer.is_valid(raise_exception=True)
            response = Response(serializer.validated_data, status=status.HTTP_200_OK)
            secure_cookie = settings.SECURE_COOKIE if not settings.DEBUG else False

            response.set_cookie(
                "access_token",
                access_token,
                httponly=True,
                secure=secure_cookie,
                samesite="Strict",
                max_age=expires_in,
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


class LogoutView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_token_repo(self):
        """요청 시마다 독립적인 TokenRepository 객체를 생성합니다."""
        return TokenRepository()

    @extend_schema(
        responses={200: OpenApiResponse(description="로그아웃 되었습니다.")},
        summary="로그아웃 API",
        description=(
            "현재 로그인한 사용자의 토큰을 모두 블랙리스트에 올리고 쿠키를 삭제합니다."
        ),
    )
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

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="토큰 갱신 성공"),
            401: OpenApiResponse(description="유효하지 않은 리프레시 토큰"),
            500: OpenApiResponse(description="서버 오류"),
        },
        summary="토큰 갱신",
        description=(
            "리프레시 토큰을 받아 새로운 엑세스 토큰과 리프레시 토큰을 발급합니다."
        ),
    )
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

    @extend_schema(
        request=CheckEmailSerializer,
        responses={200: CheckEmailSerializer},
        summary="이메일 중복 확인",
        description="이메일이 사용 가능한지 여부를 확인합니다.",
    )
    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        redis_client = get_redis_client()
        redis_repo = RedisLockRepository(redis_client=redis_client)
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service, redis_repo)

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
        redis_client = get_redis_client()
        redis_repo = RedisLockRepository(redis_client=redis_client)
        return UserService(user_repo, token_repo, token_service, redis_repo)

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={200: PasswordResetRequestSerializer},
        summary="비밀번호 재설정 요청",
        description="비밀번호 재설정 이메일을 발송합니다.",
    )
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

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={200: PasswordResetConfirmSerializer},
        summary="비밀번호 재설정 확인",
        description="비밀번호 재설정 링크를 통해 새로운 비밀번호를 설정합니다.",
    )
    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        redis_client = get_redis_client()
        redis_repo = RedisLockRepository(redis_client=redis_client)
        return UserService(user_repo, token_repo, token_service, redis_repo)

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
        except ValueError as e:
            detail_message = (
                str(e) if str(e) else "유효하지 않은 비밀번호 재설정 링크입니다."
            )
            return Response(
                {"detail": detail_message}, status=status.HTTP_401_UNAUTHORIZED
            )
