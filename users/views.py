from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from rest_framework import generics, permissions, status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import User, UserProfile
from .serializers import (
    CheckEmailSerializer,
    PasswordChangeSerializer,
    UserProfileSerializer,
    UserSerializer,
)
from .services import authenticate_user, generate_tokens, refresh_user_tokens


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get("Authorization")
        token = None

        if auth_header:
            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                raise AuthenticationFailed("Bearer 토큰이어야 합니다.")
            token = parts[1]
        else:
            token = request.COOKIES.get("access_token")

        if not token:
            raise AuthenticationFailed("인증 자격 증명이 제공되지 않았습니다.")

        try:
            payload = jwt.decode(
                token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            user = User.objects.get(id=payload["user_id"])
            if not user.is_active:
                raise AuthenticationFailed("비활성 사용자입니다.")

            # 토큰의 pwd_changed_at과 사용자의 pwd_changed_at을 비교
            token_pwd_changed_at = payload.get("pwd_changed_at")
            user_pwd_changed_at = (
                user.password_changed_at.isoformat()
                if user.password_changed_at
                else None
            )

            if token_pwd_changed_at != user_pwd_changed_at:
                raise AuthenticationFailed(
                    "비밀번호가 변경되어 토큰이 무효화되었습니다."
                )

            return (user, None)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("유효하지 않은 토큰입니다.")
        except User.DoesNotExist:
            raise AuthenticationFailed("사용자가 존재하지 않습니다.")


class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        nickname = request.data.get("nickname")
        if nickname:
            profile = getattr(user, "user_profile", None)
            if profile:
                profile.nickname = nickname
                profile.save()
            else:
                UserProfile.objects.create(user=user, nickname=nickname)

        headers = self.get_success_headers(serializer.data)
        response_data = {
            "detail": "회원가입이 성공적으로 완료되었습니다.",
            "user_id": user.id,
            "email": user.email,
        }
        return Response(response_data, status=status.HTTP_201_CREATED, headers=headers)


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")
        try:
            user = authenticate_user(email, password)
        except AuthenticationFailed as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
        except Exception:
            return Response(
                {"detail": "로그인 처리 중 오류가 발생했습니다."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        access_token, refresh_token, access_token_lifetime = generate_tokens(user)

        response = Response(
            {
                "detail": "로그인 성공",
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

    def post(self, request):
        if request.user:
            request.user.user_tokens.update(is_blacklisted=True)

        response = Response(
            {"detail": "로그아웃 되었습니다."}, status=status.HTTP_200_OK
        )
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class TokenRefreshView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # 쿠키 우선, 그 다음 Body 지원 (body 키는 refresh_token과 refresh 둘 다 시도)
        refresh_token = (
            request.COOKIES.get("refresh_token")
            or request.data.get("refresh_token")
            or request.data.get("refresh")
        )
        try:
            access_token, new_refresh_token, access_token_lifetime, user = (
                refresh_user_tokens(refresh_token)
            )
        except AuthenticationFailed as e:
            response = Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            return response
        except Exception as e:
            # 에러 메시지 명확하게 (디버깅/운영시 False로 돌리기)
            return Response(
                {"detail": f"토큰 갱신 중 오류: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response = Response(
            {
                "detail": "토큰이 성공적으로 갱신되었습니다.",
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
            max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        )
        return response


class UserProfileView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UserProfile.objects.all()
    serializer_class = UserProfileSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return UserProfile.objects.get(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"detail": "프로필이 삭제되었습니다."}, status=status.HTTP_200_OK
        )


class PasswordChangeView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
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
        user.user_tokens.update(is_blacklisted=True)

        return Response(
            {"detail": "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해주세요."},
            status=status.HTTP_200_OK,
        )


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = CheckEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
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
