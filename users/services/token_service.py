import uuid
from datetime import datetime, timezone

import jwt
from django.conf import settings
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed

from ..models import Token, User

ACCESS_TOKEN_LIFETIME = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
REFRESH_TOKEN_LIFETIME = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


def generate_tokens(user, parent_token_id=None):
    """사용자에게 새로운 액세스/리프레시 토큰 쌍을 발급합니다."""
    now = datetime.now(timezone.utc)
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

    token_obj = Token(
        user=user,
        refresh_token_id=token_id,
        issued_at=now,
        expires_at=now + REFRESH_TOKEN_LIFETIME,
        parent_token_id=parent_token_id,
    )
    token_obj.set_refresh_token(refresh_token)
    token_obj.save()

    return access_token, refresh_token, ACCESS_TOKEN_LIFETIME


def refresh_user_tokens(refresh_token):
    if not refresh_token:
        raise AuthenticationFailed("Refresh 토큰이 없습니다.")

    try:
        payload = jwt.decode(
            refresh_token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
        token_id = payload["token_id"]
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise AuthenticationFailed("유효하지 않거나 만료된 Refresh 토큰입니다.")

    try:
        with transaction.atomic():
            token_obj = Token.objects.select_for_update().get(
                refresh_token_id=token_id,
                expires_at__gt=datetime.now(timezone.utc),
                is_blacklisted=False,
            )

            if not token_obj.check_refresh_token(refresh_token):
                raise AuthenticationFailed("유효하지 않은 Refresh 토큰입니다.")

            user = token_obj.user

            access_token, new_refresh_token, access_token_lifetime = generate_tokens(
                user, parent_token_id=token_obj.refresh_token_id
            )

            token_obj.is_blacklisted = True
            token_obj.save()

    except Token.DoesNotExist:
        raise AuthenticationFailed("유효하지 않거나 만료된 Refresh 토큰입니다.")

    return access_token, new_refresh_token, access_token_lifetime, user


def is_valid_access_token(token):
    """액세스 토큰의 유효성을 검사하고 사용자 객체를 반환합니다."""
    # 반환 값 형식을 테스트와 맞추기 위해 수정합니다.
    try:
        payload = jwt.decode(
            token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
    except jwt.ExpiredSignatureError:
        return False, {"detail": "토큰이 만료되었습니다."}
    except jwt.InvalidTokenError:
        return False, {"detail": "유효하지 않은 토큰입니다."}

    try:
        user = User.objects.get(id=payload["user_id"])
        if not user.is_active:
            raise AuthenticationFailed("비활성 사용자입니다.")

        token_pwd_changed_at = payload.get("pwd_changed_at")
        user_pwd_changed_at = (
            user.password_changed_at.isoformat() if user.password_changed_at else None
        )

        if token_pwd_changed_at != user_pwd_changed_at:
            raise AuthenticationFailed("비밀번호가 변경되어 토큰이 무효화되었습니다.")
    except (User.DoesNotExist, AuthenticationFailed) as e:
        return False, {"detail": str(e)}

    return True, payload


def invalidate_refresh_token(refresh_token):
    """주어진 리프레시 토큰을 무효화합니다."""
    try:
        payload = jwt.decode(
            refresh_token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
        token_id = payload["token_id"]

        token_obj = Token.objects.get(refresh_token_id=token_id)
        token_obj.is_blacklisted = True
        token_obj.save()

    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Token.DoesNotExist):
        pass
