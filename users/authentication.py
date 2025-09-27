from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from users.exceptions import TokenAuthenticationFailed
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService

# ⚠️ 전역 객체 정의를 모두 삭제합니다. ⚠️
# user_repo = UserRepository()
# token_repo = TokenRepository()
# token_service = TokenService(user_repo, token_repo)


class JWTAuthentication(BaseAuthentication):
    """
    HTTP 헤더 또는 쿠키에서 JWT Access Token을 추출하여 사용자를 인증합니다.
    의존성 객체를 인스턴스 변수로 생성하여 테스트 격리 문제를 해결합니다.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 💡 각 인스턴스마다 독립적인 서비스 객체를 생성합니다.
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
            # 💡 인스턴스 변수에 접근하여 서비스 메서드를 호출합니다.
            payload = self.token_service.is_valid_access_token(token)
            user = self.user_repo.get_user_by_id(payload["user_id"])
            return (user, None)
        except TokenAuthenticationFailed as e:
            raise AuthenticationFailed(str(e))
        except Exception as e:
            # 개발/디버깅 시 발생하는 예기치 않은 오류를 포착합니다.
            raise AuthenticationFailed(f"인증 오류: {str(e)}")
