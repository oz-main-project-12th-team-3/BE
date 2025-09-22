from datetime import datetime, timedelta
from django.utils import timezone

import jwt
from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed

from users.models import Token, User


def generate_tokens(user: User) -> tuple[str, str]:
    if not user:
        raise ValueError("User cannot be None")
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
        "exp": timezone.now() + access_token_lifetime,
        "iat": timezone.now(),
        "pwd_changed_at": password_changed_at,
    }
    access_token = jwt.encode(
        access_token_payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm=settings.SIMPLE_JWT["ALGORITHM"]
    )

    refresh_token_payload = {
        "user_id": user.id,
        "iat": timezone.now(),
    }
    refresh_token = jwt.encode(
        refresh_token_payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm=settings.SIMPLE_JWT["ALGORITHM"]
    )

    return access_token, refresh_token


def record_refresh_token(user: User, refresh_token: str):
    """
    Saves the generated refresh token to the database.
    """
    expires_at = timezone.now() + settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]
    token = Token(user=user, issued_at=timezone.now(), expires_at=expires_at)
    token.set_refresh_token(refresh_token)
    token.save()


import hashlib

from django.db import transaction

def blacklist_token(refresh_token: str):
    """
    Blacklists a refresh token by deleting it from the database.
    """
    if refresh_token:
        try:
            hashed_token = hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()
            token = Token.objects.get(refresh_token_hash=hashed_token)
            token.delete()
        except Token.DoesNotExist:
            pass

def validate_refresh_token(token_str: str) -> User:
    """
    Validates a refresh token, locking the row to prevent race conditions.
    """
    if not token_str:
        raise AuthenticationFailed("리프레시 토큰이 제공되지 않았습니다.")

    with transaction.atomic():
        try:
            hashed_token = hashlib.sha256(token_str.encode("utf-8")).hexdigest()
            token_obj = (
                Token.objects.select_for_update()
                .select_related("user")
                .get(refresh_token_hash=hashed_token)
            )

            # Decode the token to check for expiry and signature
            jwt.decode(
                token_str,
                settings.SIMPLE_JWT["SIGNING_KEY"],
                algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
            )

            user = token_obj.user
            if not user.is_active:
                raise AuthenticationFailed("비활성화된 계정입니다.")

            return user

        except Token.DoesNotExist:
            raise AuthenticationFailed("유효하지 않거나 블랙리스트에 등록된 리프레시 토큰입니다.")
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed("만료된 리프레시 토큰입니다.")
        except jwt.InvalidTokenError:
            raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.")