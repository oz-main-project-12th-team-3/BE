from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Token, User, UserProfile
from .serializers import (
    PasswordChangeSerializer,
    TokenSerializer,
    UserProfileSerializer,
    UserSerializer,
)


def generate_tokens(user):
    # Access Token 생성
    access_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        "iat": datetime.now(timezone.utc),
    }
    access_token = jwt.encode(access_payload, settings.SECRET_KEY, algorithm="HS256")

    # Refresh Token 생성
    refresh_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm="HS256")

    return access_token, refresh_token


class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]
    MAX_LOGIN_FAILURES = 5
    LOCKOUT_DURATION_MINUTES = 30

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        two_factor_code = request.data.get("two_factor_code")

        if not email or not password:
            return Response(
                {"detail": "이메일과 비밀번호를 모두 입력해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.account_lockout_en and user.account_lockout_en > datetime.now(
            timezone.utc
        ):
            remaining = user.account_lockout_en - datetime.now(timezone.utc)
            return Response(
                {
                    "detail": (
                        f"계정이 잠겼습니다. {int(remaining.total_seconds() // 60)}분 후"
                        " 다시 시도해주세요."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not check_password(password, user.password):
            user.login_fail_count += 1
            if user.login_fail_count >= self.MAX_LOGIN_FAILURES:
                user.account_lockout_en = datetime.now(timezone.utc) + timedelta(
                    minutes=self.LOCKOUT_DURATION_MINUTES
                )
            user.save()
            return Response(
                {"detail": "비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if user.two_factor_enabled:
            if not two_factor_code:
                return Response(
                    {"detail": "2단계 인증 코드를 입력해주세요."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if two_factor_code != "123456":
                return Response(
                    {"detail": "2단계 인증 코드가 올바르지 않습니다."},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        user.login_fail_count = 0
        user.save()

        access_token, refresh_token = generate_tokens(user)

        Token.objects.create(
            user=user,
            refresh_token=refresh_token,
            issued_at=datetime.fromtimestamp(
                jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])[
                    "iat"
                ],
                tz=timezone.utc,
            ),
            expires_at=datetime.fromtimestamp(
                jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])[
                    "exp"
                ],
                tz=timezone.utc,
            ),
        )

        return Response(
            {
                "user_id": user.id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expires_in": 3600,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh_token")
        if not refresh_token:
            return Response(
                {"detail": "리프레시 토큰이 필요합니다."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = Token.objects.get(refresh_token=refresh_token)
            token.delete()
        except Token.DoesNotExist:
            pass

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserProfileView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "user_id"

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        if self.request.user.id != user_id:
            raise AuthenticationFailed("자신의 프로필만 수정할 수 있습니다.")
        return super().get_object()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"detail": "프로필이 삭제되었습니다."}, status=status.HTTP_200_OK
        )


class TokenDetailView(generics.RetrieveDestroyAPIView):
    queryset = Token.objects.all()
    serializer_class = TokenSerializer
    permission_classes = [permissions.IsAuthenticated]


class PasswordChangeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, id):
        serializer = PasswordChangeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response(
                {"detail": "사용자를 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if request.user.id != user.id:
            return Response(
                {"detail": "권한이 없습니다."}, status=status.HTTP_403_FORBIDDEN
            )

        current_password = serializer.validated_data["current_password"]
        new_password = serializer.validated_data["new_password"]

        if not check_password(current_password, user.password):
            return Response(
                {"detail": "현재 비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user.set_password(new_password)
        user.save()

        return Response(
            {"detail": "비밀번호가 성공적으로 변경되었습니다."},
            status=status.HTTP_200_OK,
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

        exists = User.objects.filter(email=email).exists()
        if exists:
            return Response(
                {"available": False, "detail": "이미 사용중인 이메일입니다."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"available": True, "detail": "사용 가능한 이메일입니다."},
                status=status.HTTP_200_OK,
            )
