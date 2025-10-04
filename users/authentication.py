from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.exceptions import TokenAuthenticationFailed
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService


class JWTAuthentication(BaseAuthentication):
    """
    HTTP 헤더 또는 쿠키에서 JWT Access Token을 추출하여 사용자를 인증.
    (정식 토큰 전용)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()
        self.token_service = TokenService(self.user_repo, self.token_repo)

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
            return None

        try:
            # is_valid_access_token: 'is_temporary' 필드가 없거나 False인 정식 토큰.
            payload = self.token_service.is_valid_access_token(token)

            # 안전장치: 정식 JWTAuthentication에서는 임시 토큰 거부.
            if payload.get("is_temporary", False):
                raise AuthenticationFailed(
                    "임시 토큰으로는 일반 엔드포인트에 접근할 수 없습니다."
                )

            user = self.user_repo.get_user_by_id(payload["user_id"])
            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            raise AuthenticationFailed(f"인증 오류: {str(e)}")


# -----------------------------------------------------------
#  TfaApiView용 TemporaryJWTAuthentication
# -----------------------------------------------------------


class TemporaryJWTAuthentication(BaseAuthentication):
    """
    HTTP 쿠키에서 'is_temporary': True인 JWT Access Token을 추출하여 사용자 인증.
    2FA 설정 또는 인증 단계에서만 사용.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_repo = UserRepository()
        self.token_repo = TokenRepository()
        self.token_service = TokenService(self.user_repo, self.token_repo)

    def authenticate(self, request):
        # TfaApiView는 쿠키에 있는 임시 토큰을 사용하도록 설계.
        token = request.COOKIES.get("access_token")

        if not token:
            return None

        try:
            # is_valid_access_token은 JWT 디코딩 및 만료 검증을 수행.
            payload = self.token_service.is_valid_access_token(token)

            # 임시 토큰(is_temporary: True)인지 확인
            if not payload.get("is_temporary", False):
                raise AuthenticationFailed(
                    "정식 토큰으로는 2FA 엔드포인트에 접근할 수 없습니다."
                )

            user = self.user_repo.get_user_by_id(payload["user_id"])

            # 세션 기반 상태 검증은 TfaApiView에서 진행.
            # -> 여기서는 임시 토큰이 유효한지만 확인하고 통과.

            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            raise AuthenticationFailed(f"임시 토큰 인증 오류: {str(e)}")
