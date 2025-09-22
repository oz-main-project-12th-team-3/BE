from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings

from rest_framework.exceptions import AuthenticationFailed
from users.models import User, Token


def validate_refresh_token(token_str: str) -> User:
    """
    Validates a refresh token.

    Checks for existence in DB, decodes it to check expiry and signature.
    Returns the associated user if valid.

    Raises:
        AuthenticationFailed: If the token is invalid, expired, or not found.
    """
    if not token_str:
        raise AuthenticationFailed("리프레시 토큰이 제공되지 않았습니다.")

    try:
        # Check if token exists in our database (hasn't been blacklisted)
        token_obj = Token.objects.select_related("user").get(refresh_token=token_str)
    except Token.DoesNotExist:
        raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.")

    try:
        # Decode the token to check for expiry and signature
        jwt.decode(token_str, settings.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("만료된 리프레시 토큰입니다.")
    except jwt.InvalidTokenError:
        raise AuthenticationFailed("유효하지 않은 리프레시 토큰입니다.")

    # Check if the associated user is active
    if not token_obj.user.is_active:
        raise AuthenticationFailed("비활성화된 계정입니다.")

    return token_obj.user

def blacklist_token(refresh_token: str):
    """
    Blacklists a refresh token by deleting it from the database.
    """
    if refresh_token:
        try:
            token = Token.objects.get(refresh_token=refresh_token)
            token.delete()
        except Token.DoesNotExist:
            # Token already blacklisted or never existed, which is fine for logout
            pass
