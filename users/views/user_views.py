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
from ..services.token_service import TokenService
from ..services.user_service import UserService

# ⚠️ 전역 객체 선언 제거:
# user_repo = UserRepository()
# token_repo = TokenRepository()
# token_service = TokenService(user_repo, token_repo)
# user_service = UserService(user_repo, token_repo, token_service)


class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def get(self, request):
        user_service = self._get_user_service()
        profile = user_service.get_user_profile(request.user)
        if not profile:
            return Response(
                {"detail": "프로필을 찾을 수 없습니다."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserProfileSerializer(profile)
        return Response(serializer.data)

    def patch(self, request):
        user_service = self._get_user_service()
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
        user_service = self._get_user_service()
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

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def patch(self, request):
        user_service = self._get_user_service()
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        new_password = serializer.validated_data["new_password"]

        # 비밀번호 변경 시 PasswordMismatchException 발생 시 자동으로 처리됨
        user_service.change_user_password(user, new_password)

        response = Response(
            {"detail": "비밀번호가 성공적으로 변경되었습니다. 다시 로그인해 주세요."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token")
        return response


class UserDeleteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        return UserService(user_repo, token_repo, token_service)

    def post(self, request):
        user_service = self._get_user_service()
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
