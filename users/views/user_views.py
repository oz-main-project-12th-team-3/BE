from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..authentication import JWTAuthentication
from ..exceptions import PasswordMismatchException
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import (
    PasswordChangeSerializer,
    UserProfileSerializer,
)
from ..services.user_service import UserService

# 의존성 주입
user_repo = UserRepository()
token_repo = TokenRepository()
user_service = UserService(user_repo, token_repo)


class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = user_service.get_user_profile(request.user)
        if not profile:
            return Response(
                {"detail": "프로필을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        profile = user_service.get_user_profile(request.user)
        if not profile:
            return Response(
                {"detail": "프로필을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request):
        profile = user_service.get_user_profile(request.user)
        if not profile:
            return Response(
                {"detail": "프로필을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        profile.delete()
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

        try:
            access_token, refresh_token, access_token_lifetime = (
                user_service.change_user_password(user, current_password, new_password)
            )
            response = Response(
                {
                    "detail": "비밀번호가 성공적으로 변경되었습니다.",
                    "access_token": access_token,
                    "refresh_token": refresh_token,
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
                max_age=int(
                    settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()
                ),
            )
            return response
        except PasswordMismatchException as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)


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

        try:
            user_service.delete_user(request.user, password)
            response = Response(
                {"detail": "회원탈퇴가 성공적으로 처리되었습니다."},
                status=status.HTTP_200_OK,
            )
            response.delete_cookie("access_token")
            response.delete_cookie("refresh_token")
            return response
        except PasswordMismatchException as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
