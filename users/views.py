from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.http import Http404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import JWTAuthentication
from .models import User
from .serializers import (
    PasswordChangeSerializer,
    UserProfileSerializer,
    UserSerializer,
)
from .services import token_service, user_service

# --- Views based on HEAD branch architecture ---


class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        # Use user_service to create user and profile
        user = user_service.create_user(**validated_data)

        response_data = {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "is_active": user.is_active,
            "two_factor_enabled": user.two_factor_enabled,
            "created_at": user.created_at.isoformat(),
            "detail": "회원가입이 성공적으로 완료되었습니다.",
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        two_factor_code = request.data.get("two_factor_code")

        try:
            user = user_service.authenticate_user(
                email=email, password=password, two_factor_code=two_factor_code
            )

            access_token, refresh_token = token_service.generate_tokens(user)
            token_service.record_refresh_token(user, refresh_token)

            response_data = {
                "access_token": access_token,
                "expires_in": int(
                    settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
                ),
                "detail": "로그인에 성공했습니다.",
            }
            response = Response(response_data, status=status.HTTP_200_OK)

            # Set refresh_token in a secure cookie
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                expires=datetime.now(timezone.utc)
                + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"],
            )
            # Also set access_token for convenience, though Authorization header is standard
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                expires=datetime.now(timezone.utc)
                + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )

            return response

        except (AuthenticationFailed, PermissionDenied) as e:
            return Response({"detail": e.detail}, status=e.status_code)
        except Exception:
            return Response(
                {"detail": "로그인 중 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        try:
            user = token_service.validate_refresh_token(refresh_token)
            access_token, _ = token_service.generate_tokens(user)

            response = Response(
                {
                    "access_token": access_token,
                    "expires_in": int(
                        settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
                    ),
                    "detail": "액세스 토큰이 성공적으로 갱신되었습니다.",
                },
                status=status.HTTP_200_OK,
            )
            # Re-set the access token cookie
            response.set_cookie(
                key="access_token",
                value=access_token,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
                expires=datetime.now(timezone.utc)
                + settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"],
            )
            return response

        except AuthenticationFailed as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")
        token_service.blacklist_token(refresh_token)

        response = Response(
            {"detail": "로그아웃에 성공했습니다."}, status=status.HTTP_200_OK
        )
        response.delete_cookie("refresh_token")
        response.delete_cookie("access_token")

        if hasattr(request, "session"):
            logout(request)

        return response


class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserProfileSerializer

    def get(self, request):
        try:
            profile = user_service.get_user_profile(
                actor=request.user, target_user_id=request.user.id
            )
            serializer = self.serializer_class(profile)
            return Response(serializer.data)
        except (PermissionDenied, Http404) as e:
            status_code = (
                status.HTTP_403_FORBIDDEN
                if isinstance(e, PermissionDenied)
                else status.HTTP_404_NOT_FOUND
            )
            return Response({"detail": str(e)}, status=status_code)

    def patch(self, request):
        serializer = self.serializer_class(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)

        try:
            profile = user_service.update_user_profile(
                actor=request.user,
                target_user_id=request.user.id,
                **serializer.validated_data,
            )
            response_serializer = self.serializer_class(profile)
            return Response(response_serializer.data)
        except (PermissionDenied, Http404) as e:
            status_code = (
                status.HTTP_403_FORBIDDEN
                if isinstance(e, PermissionDenied)
                else status.HTTP_404_NOT_FOUND
            )
            return Response({"detail": str(e)}, status=status_code)

    def delete(self, request):
        try:
            user_service.delete_user(actor=request.user, target_user_id=request.user.id)
            return Response(
                {"message": "유저 프로필 삭제가 완료되었습니다."},
                status=status.HTTP_204_NO_CONTENT,
            )
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)


class PasswordChangeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        target_user_id = request.user.id

        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        try:
            user_service.change_user_password(
                actor=request.user,
                target_user_id=target_user_id,
                current_password=validated_data["current_password"],
                new_password=validated_data["new_password"],
            )

            # Invalidate all tokens by blacklisting them after password change
            token_service.blacklist_token(request.COOKIES.get("refresh_token"))

            response = Response(
                {
                    "detail": "비밀번호가 성공적으로 변경되었습니다. "
                    "다시 로그인해주세요."
                },
                status=status.HTTP_200_OK,
            )
            response.delete_cookie("refresh_token")
            response.delete_cookie("access_token")
            return response

        except (ValidationError, AuthenticationFailed, PermissionDenied) as e:
            if isinstance(e, ValidationError):
                return Response(
                    {"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST
                )
            return Response({"detail": e.detail}, status=e.status_code)
        except Exception:
            return Response(
                {"detail": "비밀번호 변경 중 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response(
                {"detail": "이메일을 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST
            )

        email_exists = user_service.check_email_availability(email)

        if email_exists:
            return Response(
                {"available": False, "detail": "이미 사용중인 이메일입니다."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"available": True, "detail": "사용 가능한 이메일입니다."},
                status=status.HTTP_200_OK,
            )
