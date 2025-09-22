from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth import logout
from django.contrib.auth.hashers import check_password
from rest_framework import generics, permissions, status
from django.core.exceptions import ValidationError
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Token, User, UserProfile
from .serializers import (
    PasswordChangeSerializer,
    TokenSerializer,
    UserProfileSerializer,
    UserSerializer,
)
from .services import token_service, user_service
from .services.user_service import create_user





class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        email = validated_data.pop("email")
        password = validated_data.pop("password")
        nickname = validated_data.pop("nickname")

        user = create_user(email=email, password=password, nickname=nickname, **validated_data)

        # Construct a response that matches the API specification
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
            # 1. Call authentication service
            user = user_service.authenticate_user(
                email=email, password=password, two_factor_code=two_factor_code
            )

            # 2. Generate and record tokens
            access_token, refresh_token = token_service.generate_tokens(user)
            token_service.record_refresh_token(user, refresh_token)

            # 3. Build response body and set cookie
            response_data = {
                "access_token": access_token,
                "expires_in": 3600,  # TODO: Get from settings
                "detail": "로그인에 성공했습니다.",
            }
            response = Response(response_data, status=status.HTTP_200_OK)
            response.set_cookie(
                key="refresh_token",
                value=refresh_token,
                httponly=True,
                secure=not settings.DEBUG,  # True in production
                samesite="Lax",
                expires=datetime.now(timezone.utc) + timedelta(days=7),
            )

            return response

        except (AuthenticationFailed, PermissionDenied) as e:
            # Catch exceptions from the service layer and return them as DRF responses
            return Response({"detail": e.detail}, status=e.status_code)
        except Exception as e:
            # Generic fallback for other unexpected errors
            return Response(
                {"detail": "로그인 중 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class TokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]  # Anyone can attempt to refresh

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        try:
            # 1. Validate the refresh token and get the user
            user = token_service.validate_refresh_token(refresh_token)

            # 2. Generate a new access token (only)
            access_token, _ = token_service.generate_tokens(user)

            # 3. Build and return response
            return Response(
                {
                    "access_token": access_token,
                    "expires_in": 3600,  # TODO: Get from settings
                    "detail": "액세스 토큰이 성공적으로 갱신되었습니다.",
                },
                status=status.HTTP_200_OK,
            )

        except AuthenticationFailed as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        # Blacklist the refresh token if provided in the cookie
        refresh_token = request.COOKIES.get("refresh_token")
        token_service.blacklist_token(refresh_token)

        # Create a response and delete the cookie on the client side
        response = Response({"detail": "로그아웃에 성공했습니다."}, status=status.HTTP_200_OK)
        response.delete_cookie("refresh_token")

        # Also perform Django's session logout if applicable
        if hasattr(request, "session"):
            logout(request)

        return response


class UserProfileView(APIView):
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
                actor=request.user, target_user_id=request.user.id, **serializer.validated_data
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
            return Response({"message": "유저 프로필 삭제가 완료되었습니다."})
        except PermissionDenied as e:
            return Response({"detail": str(e)}, status=status.HTTP_403_FORBIDDEN)


class TokenDetailView(generics.RetrieveDestroyAPIView):
    queryset = Token.objects.all()
    serializer_class = TokenSerializer
    permission_classes = [permissions.IsAuthenticated]


class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Note: The URL should be /users/me/password, so id is not needed from URL
        target_user_id = request.user.id

        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        try:
            user = user_service.change_user_password(
                actor=request.user,
                target_user_id=target_user_id,
                current_password=validated_data["current_password"],
                new_password=validated_data["new_password"],
            )
            
            # Construct response based on API spec
            response_data = {
                "id": user.id,
                "email": user.email,
                "two_factor_enabled": user.two_factor_enabled,
                "password_changed_at": user.password_changed_at.isoformat() if user.password_changed_at else None,
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except (ValidationError, AuthenticationFailed, PermissionDenied) as e:
            if isinstance(e, ValidationError):
                return Response({"detail": e.messages}, status=status.HTTP_400_BAD_REQUEST)
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
                {"detail": "이메일을 입력해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
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
