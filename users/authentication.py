import jwt
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .models import User
from .services.token_service import is_valid_access_token


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
            is_valid, payload = is_valid_access_token(
                token
            )  # is_valid_access_token의 반환 값 변경
            if not is_valid:
                raise AuthenticationFailed("유효하지 않은 토큰입니다.")

            user = User.objects.get(id=payload["user_id"])
            return (user, None)
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("유효하지 않은 토큰입니다.")
        except User.DoesNotExist:
            raise AuthenticationFailed("사용자가 존재하지 않습니다.")
