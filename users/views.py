from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from rest_framework import generics, permissions, status
from rest_framework.authentication import BaseAuthentication
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
    access_token_lifetime = timedelta(minutes=30)
    refresh_token_lifetime = timedelta(days=7)
    jwt_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + access_token_lifetime,
        "iat": datetime.now(timezone.utc),
    }
    access_token = jwt.encode(jwt_payload, settings.SECRET_KEY, algorithm="HS256")
    refresh_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + refresh_token_lifetime,
        "iat": datetime.now(timezone.utc),
    }
    refresh_token = jwt.encode(refresh_payload, settings.SECRET_KEY, algorithm="HS256")
    Token.objects.create(
        user=user,
        refresh_token=refresh_token,
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + refresh_token_lifetime,
    )
    return access_token, refresh_token, access_token_lifetime


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        token = None
        if auth_header:
            try:
                prefix, token = auth_header.split(" ")
                if prefix.lower() != "bearer":
                    raise AuthenticationFailed("Bearer 토큰이어야 합니다.")
            except ValueError:
                raise AuthenticationFailed(
                    "유효하지 않은 Authorization 헤더 형식입니다."
                )
        else:
            token = request.COOKIES.get("access_token")
        if not token:
            return None
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
            user = User.objects.get(id=payload["user_id"])
            return (user, None)
        except (jwt.ExpiredSignatureError, jwt.DecodeError, User.DoesNotExist):
            raise AuthenticationFailed("유효하지 않은 토큰입니다.")


class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        response.data = {
            "detail": "회원가입이 성공적으로 완료되었습니다.",
            **response.data,
        }
        return response


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
                        "계정이 잠겼습니다. "
                        f"{int(remaining.total_seconds() // 60)}분 후 "
                        "다시 시도해주세요."
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

        access_token, refresh_token, access_token_lifetime = generate_tokens(user)

        response = Response(
            {
                "detail": "로그인 성공",
                "user_id": user.id,
                "expires_in": int(access_token_lifetime.total_seconds()),
            },
            status=status.HTTP_200_OK,
        )
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=settings.SECURE_COOKIE,
            samesite="Lax",
            max_age=int(access_token_lifetime.total_seconds()),
        )
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=settings.SECURE_COOKIE,
            samesite="Lax",
            max_age=7 * 24 * 60 * 60,
        )
        return response


class LogoutView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        response = Response(
            {"detail": "로그아웃 되었습니다."}, status=status.HTTP_200_OK
        )
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class UserProfileView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        user_id = self.kwargs.get("user_id")
        return UserProfile.objects.get(user__id=user_id)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"detail": "프로필이 삭제되었습니다."}, status=status.HTTP_200_OK
        )


class TokenDetailView(generics.RetrieveDestroyAPIView):
    queryset = Token.objects.all()
    serializer_class = TokenSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response({"detail": "토큰이 삭제되었습니다."}, status=status.HTTP_200_OK)


class PasswordChangeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, id):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
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
        user.password_changed_at = datetime.now(timezone.utc)
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
                {"detail": "이메일을 입력해주세요."}, status=status.HTTP_400_BAD_REQUEST
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
