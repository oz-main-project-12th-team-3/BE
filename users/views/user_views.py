from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from utils.redis_client import get_redis_client

from ..authentication import JWTAuthentication
from ..exceptions import PasswordMismatchException
from ..repositories.login_fail_lock_repository import LoginFailLockRepository
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository
from ..serializers import PasswordChangeSerializer, UserProfileSerializer
from ..services.token_service import TokenService
from ..services.user_service import UserService


class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [permissions.IsAuthenticated]

    def _get_user_service(self):
        """요청 시마다 독립적인 UserService 객체를 생성합니다."""
        user_repo = UserRepository()
        token_repo = TokenRepository()
        token_service = TokenService(user_repo, token_repo)
        redis_client = get_redis_client()
        redis_repo = LoginFailLockRepository(redis_client=redis_client)  # 변경사항 반영
        return UserService(user_repo, token_repo, token_service, redis_repo)

    @extend_schema(
        responses={
            200: OpenApiResponse(description="사용자 프로필 정보"),
            404: OpenApiResponse(description="프로필을 찾을 수 없습니다."),
        },
        summary="사용자 프로필 조회",
        description="인증된 사용자의 프로필 정보를 조회합니다.",
    )
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

    @extend_schema(
        request=UserProfileSerializer,
        responses={
            200: OpenApiResponse(description="수정된 사용자 프로필 정보"),
            400: OpenApiResponse(description="잘못된 요청"),
            404: OpenApiResponse(description="프로필을 찾을 수 없습니다."),
        },
        summary="사용자 프로필 부분 수정",
        description="인증된 사용자의 프로필 정보를 부분 수정합니다.",
    )
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

    @extend_schema(
        responses={
            200: OpenApiResponse(description="프로필이 삭제되었습니다."),
            404: OpenApiResponse(description="프로필을 찾을 수 없습니다."),
        },
        summary="사용자 프로필 삭제",
        description="인증된 사용자의 프로필을 삭제합니다.",
    )
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
        redis_client = get_redis_client()
        redis_repo = LoginFailLockRepository(redis_client=redis_client)  # 변경사항 반영
        return UserService(user_repo, token_repo, token_service, redis_repo)

    @extend_schema(
        request=PasswordChangeSerializer,
        responses={
            200: OpenApiResponse(description="비밀번호가 성공적으로 변경되었습니다."),
            400: OpenApiResponse(description="잘못된 요청"),
            401: OpenApiResponse(description="비밀번호 불일치 오류"),
        },
        summary="비밀번호 변경",
        description="사용자의 비밀번호를 변경하고 인증 토큰은 삭제합니다.",
    )
    def patch(self, request):
        user_service = self._get_user_service()
        serializer = PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        new_password = serializer.validated_data["new_password"]

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
        redis_client = get_redis_client()
        redis_repo = LoginFailLockRepository(redis_client=redis_client)  # 변경사항 반영
        return UserService(user_repo, token_repo, token_service, redis_repo)

    @extend_schema(
        request={
            "type": "object",
            "properties": {
                "password": {
                    "type": "string",
                    "description": "사용자 비밀번호",
                }
            },
            "required": ["password"],
        },
        responses={
            200: OpenApiResponse(description="회원탈퇴가 성공적으로 처리되었습니다."),
            400: OpenApiResponse(description="비밀번호 미입력 등 잘못된 요청"),
            401: OpenApiResponse(description="비밀번호 불일치 오류"),
        },
        summary="회원탈퇴",
        description="사용자가 비밀번호를 확인 후 회원탈퇴를 진행합니다.",
    )
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
