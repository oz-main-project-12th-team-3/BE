from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .exceptions import TokenAuthenticationFailed
from .repositories.token_repository import TokenRepository
from .repositories.user_repository import UserRepository
from .services.token_service import TokenService

# 의존성 주입
user_repo = UserRepository()
token_repo = TokenRepository()
token_service = TokenService(user_repo, token_repo)


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
            return None

        try:
            payload = token_service.is_valid_access_token(token)
            user = user_repo.get_user_by_id(payload["user_id"])
            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            raise AuthenticationFailed(f"인증 오류: {str(e)}")
