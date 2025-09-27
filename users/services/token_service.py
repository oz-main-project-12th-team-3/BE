import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from ..exceptions import TokenAuthenticationFailed, UserNotFoundException
from ..repositories.token_repository import TokenRepository
from ..repositories.user_repository import UserRepository

ACCESS_TOKEN_LIFETIME = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
REFRESH_TOKEN_LIFETIME = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


class TokenService:
    def __init__(self, user_repo: UserRepository, token_repo: TokenRepository):
        self.user_repo = user_repo
        self.token_repo = token_repo

    def generate_tokens(self, user, parent_token_id=None):
        now = datetime.now(dt_timezone.utc)
        token_id = uuid.uuid4()

        access_token_payload = {
            "user_id": user.id,
            "exp": now + ACCESS_TOKEN_LIFETIME,
            "iat": now,
            "pwd_changed_at": user.password_changed_at.isoformat()
            if user.password_changed_at
            else None,
        }
        access_token = jwt.encode(
            access_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        refresh_token_payload = {
            "token_id": str(token_id),
            "user_id": user.id,
            "exp": now + REFRESH_TOKEN_LIFETIME,
            "iat": now,
        }
        refresh_token = jwt.encode(
            refresh_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        self.token_repo.create_token(
            user,
            token_id,
            refresh_token,
            now,
            now + REFRESH_TOKEN_LIFETIME,
            parent_token_id,
        )

        return access_token, refresh_token, ACCESS_TOKEN_LIFETIME

    def generate_temporary_tokens(self, user):
        now = datetime.now(dt_timezone.utc)
        token_id = uuid.uuid4()

        temp_access_lifetime = timedelta(minutes=5)

        access_token_payload = {
            "user_id": user.id,
            "exp": now + temp_access_lifetime,
            "iat": now,
            "pwd_changed_at": user.password_changed_at.isoformat()
            if user.password_changed_at
            else None,
            "is_temporary": True,
        }
        access_token = jwt.encode(
            access_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        refresh_token_payload = {
            "token_id": str(token_id),
            "user_id": user.id,
            "exp": now + REFRESH_TOKEN_LIFETIME,
            "iat": now,
            "is_temporary": True,
        }
        refresh_token = jwt.encode(
            refresh_token_payload,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithm=settings.SIMPLE_JWT["ALGORITHM"],
        )

        self.token_repo.create_token(
            user,
            token_id,
            refresh_token,
            now,
            now + REFRESH_TOKEN_LIFETIME,
            parent_token_id=None,
        )

        return access_token, refresh_token, temp_access_lifetime

    def refresh_user_tokens(self, refresh_token):
        if not refresh_token:
            raise TokenAuthenticationFailed("Refresh 토큰이 없습니다.")

        try:
            payload = jwt.decode(
                refresh_token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            token_id = payload["token_id"]
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            raise TokenAuthenticationFailed(
                "유효하지 않거나 만료된 Refresh 토큰입니다."
            )

        token_obj = self.token_repo.get_valid_token_by_id(token_id)

        if not token_obj.check_refresh_token(refresh_token):
            raise TokenAuthenticationFailed("유효하지 않은 Refresh 토큰입니다.")

        user = token_obj.user

        access_token, new_refresh_token, access_token_lifetime = self.generate_tokens(
            user, parent_token_id=token_obj.refresh_token_id
        )

        self.token_repo.blacklist_token(token_obj)

        return access_token, new_refresh_token, access_token_lifetime, user

    def is_valid_access_token(self, token):
        try:
            payload = jwt.decode(
                token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
        except jwt.ExpiredSignatureError:
            raise TokenAuthenticationFailed("토큰이 만료되었습니다.")
        except jwt.InvalidTokenError:
            raise TokenAuthenticationFailed("유효하지 않은 토큰입니다.")

        user_id = payload.get("user_id")
        if not user_id:
            raise TokenAuthenticationFailed("유효하지 않은 토큰입니다.")

        try:
            user = self.user_repo.get_user_by_id(user_id)
        except UserNotFoundException:
            raise TokenAuthenticationFailed("사용자가 존재하지 않습니다.")

        if not user.is_active:
            raise TokenAuthenticationFailed("비활성 사용자입니다.")

        token_pwd_changed_at_str = payload.get("pwd_changed_at")
        if token_pwd_changed_at_str:
            token_pwd_changed_at = datetime.fromisoformat(token_pwd_changed_at_str)
            # aware가 아니면 UTC 기준 aware로 만들어주기
            if timezone.is_naive(token_pwd_changed_at):
                token_pwd_changed_at = timezone.make_aware(
                    token_pwd_changed_at, timezone.utc
                )
        else:
            token_pwd_changed_at = None

        user_pwd_changed_at = user.password_changed_at
        if timezone.is_naive(user_pwd_changed_at):
            user_pwd_changed_at = timezone.make_aware(user_pwd_changed_at, timezone.utc)

        if token_pwd_changed_at != user_pwd_changed_at:
            raise TokenAuthenticationFailed(
                "비밀번호가 변경되어 토큰이 무효화되었습니다."
            )

        if payload.get("is_temporary"):
            # 임시 토큰 처리 로직 가능
            pass

        return payload

    def invalidate_refresh_token(self, refresh_token):
        try:
            payload = jwt.decode(
                refresh_token,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )
            token_id = payload["token_id"]
            token_obj = self.token_repo.get_valid_token_by_id(token_id)
            self.token_repo.blacklist_token(token_obj)
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, AuthenticationFailed):
            pass
