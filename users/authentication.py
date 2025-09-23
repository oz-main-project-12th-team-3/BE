import jwt
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from django.contrib.auth import get_user_model


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        User = get_user_model()
        auth_header = request.headers.get("Authorization")
        token = None

        if auth_header:
            parts = auth_header.split(" ", 1)
            if len(parts) != 2 or parts[0].lower() != "bearer":
                return None
            token = parts[1]
        else:
            token = request.COOKIES.get("access_token")

        if not token:
            return None

        try:
            payload = jwt.decode(
                token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            user = User.objects.get(id=payload["user_id"])
            if not user.is_active:
                raise AuthenticationFailed("비활성 사용자입니다.")

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
        except (jwt.InvalidTokenError, User.DoesNotExist):
            raise AuthenticationFailed("유효하지 않은 토큰입니다.")
