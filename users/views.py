from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as django_login
from rest_framework import generics, permissions, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import JWTAuthentication
from .models import User, UserProfile
from .serializers import (
    CheckEmailSerializer,
    PasswordChangeSerializer,
    UserLoginSerializer,
    UserProfileSerializer,
    UserRegisterSerializer,
)
from .services.token_service import generate_tokens, refresh_user_tokens
from .services.user_service import (
    change_user_password,
    check_email_exists,
    create_user,
    delete_user,
)


class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer  # Change this line
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")
        nickname = serializer.validated_data.get("nickname")

        user = create_user(email, password, nickname)

        response_data = {
            "detail": "회원가입이 성공적으로 완료되었습니다.",
            "user_id": user.id,
            "email": user.email,
        }
        return Response(response_data, status=status.HTTP_201_CREATED)


class UserLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        password = serializer.validated_data.get("password")

        user = authenticate(request, username=email, password=password)
        if user:
            django_login(request, user)  # Django의 세션 기반 로그인을 사용
            # 이 시점에서, 2FA가 활성화된 사용자는
            # `django_otp.middleware.OTPMiddleware`에 의해 OTP 입력 페이지로
            # 자동으로 리디렉션됩니다.
            # 2FA가 없는 사용자는 아래 코드가 실행됨
            access_token, refresh_token, access_token_lifetime = generate_tokens(user)
            # ... 토큰 발급 및 쿠키 설정 코드 그대로
            response = Response(
                {
                    "detail": "로그인 성공",
                    "user_id": user.id,
                    "expires_in": int(access_token_lifetime.total_seconds()),
                },
                status=status.HTTP_200_OK,
            )
            # 쿠키 설정
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
        else:
            return Response(
                {"detail": "이메일 또는 비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


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
        refresh_token = (
            request.COOKIES.get("refresh_token")
            or request.data.get("refresh_token")
            or request.data.get("refresh")
        )
        try:
            (
                access_token,
                new_refresh_token,
                access_token_lifetime,
                user,
            ) = refresh_user_tokens(refresh_token)
        except AuthenticationFailed as e:
            response = Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            return response
        except Exception as e:
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

        if change_user_password(user, current_password, new_password):
            return Response(
                {
                    "detail": (
                        "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해주세요."
                    )
                },
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"detail": "현재 비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )


class CheckEmailView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = CheckEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data.get("email")
        if check_email_exists(email):
            return Response(
                {"available": False, "detail": "이미 사용중인 이메일입니다."},
                status=status.HTTP_200_OK,
            )
        else:
            return Response(
                {"available": True, "detail": "사용 가능한 이메일입니다."},
                status=status.HTTP_200_OK,
            )


class UserDeleteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        password = request.data.get("password")
        if not password:
            return Response(
                {"detail": "비밀번호를 입력해주세요."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        if delete_user(user, password):
            response = Response(
                {"detail": "회원탈퇴가 성공적으로 처리되었습니다."},
                status=status.HTTP_200_OK,
            )
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            return response
        else:
            return Response(
                {"detail": "비밀번호가 올바르지 않습니다."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
