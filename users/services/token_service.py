from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

from users.models import Token, User


def generate_tokens(user: User) -> tuple[str, str]:
    """
    Generates access and refresh tokens for a given user, including password change claim.
    """
    access_token_lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
    refresh_token_lifetime = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]

    # Include password changed timestamp in the payload for validation
    password_changed_at = (
        user.password_changed_at.isoformat() if user.password_changed_at else None
    )

    access_token_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + access_token_lifetime,
        "iat": datetime.now(timezone.utc),
        "pwd_changed_at": password_changed_at,
    }
    access_token = jwt.encode(
        access_token_payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm=settings.SIMPLE_JWT["ALGORITHM"]
    )

    refresh_token_payload = {
        "user_id": user.id,
        "exp": datetime.now(timezone.utc) + refresh_token_lifetime,
        "iat": datetime.now(timezone.utc),
    }
    refresh_token = jwt.encode(
        refresh_token_payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm=settings.SIMPLE_JWT["ALGORITHM"]
    )

    return access_token, refresh_token


def record_refresh_token(user: User, refresh_token: str):
    """
    Saves the generated refresh token to the database.
    """
    expires_at = datetime.now(timezone.utc) + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    Token.objects.create(
        user=user,
        refresh_token=refresh_token,
        issued_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )


def validate_refresh_token(token_str: str) -> User:
    """
    Validates a refresh token.
    """
    if not token_str:
        raise AuthenticationFailed("리프레시 토큰이 제공되지 않았습니다.")

    try:
        token_obj = Token.objects.select_related("user").get(refresh_token=token_str)
    except Token.DoesNotExist:
        raise AuthenticationFailed("유효하지 않거나 블랙리스트에 등록된 리프레시 토큰입니다.")

    try:
        payload = jwt.decode(
            token_str,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("만료된 리프레시 토큰입니다.")
    except jwt.InvalidTokenError:
        raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.")

    user = token_obj.user
    if not user.is_active:
        raise AuthenticationFailed("비활성화된 계정입니다.")

    return user


def blacklist_token(refresh_token: str):
    """
    Blacklists a refresh token by deleting it from the database.
    """
    if refresh_token:
        try:
            token = Token.objects.get(refresh_token=refresh_token)
            token.delete()
        except Token.DoesNotExist:
            pass