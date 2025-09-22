import uuid
from datetime import datetime, timedelta, timezone

import jwt
from django.conf import settings
from django.contrib.auth.hashers import check_password
from rest_framework.exceptions import AuthenticationFailed

from .models import Token, User

ACCESS_TOKEN_LIFETIME = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
REFRESH_TOKEN_LIFETIME = settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"]


def generate_tokens(user, parent_token_id=None):
    now = datetime.now(timezone.utc)
    token_id = uuid.uuid4()  # 고유한 UUID 생성

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
        "token_id": str(token_id),  # 페이로드에 UUID 포함
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
        refresh_token_id=token_id,  # UUID 저장
        issued_at=now,
        expires_at=now + REFRESH_TOKEN_LIFETIME,
        parent_token_id=parent_token_id,
    )
    token_obj.set_refresh_token(refresh_token)
    token_obj.save()

    return access_token, refresh_token, ACCESS_TOKEN_LIFETIME


def authenticate_user(email, password):
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise AuthenticationFailed("사용자를 찾을 수 없습니다.")

    if not user.is_active:
        raise AuthenticationFailed("비활성 사용자입니다.")

    if user.is_account_locked():
        raise AuthenticationFailed("계정이 잠겼습니다. 잠시 후 다시 시도해주세요.")

    if not check_password(password, user.password):
        user.login_fail_count += 1
        if user.login_fail_count >= 5:
            user.account_locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=30
            )
        user.save(update_fields=["login_fail_count", "account_locked_until"])
        raise AuthenticationFailed("비밀번호가 올바르지 않습니다.")

    user.login_fail_count = 0
    user.save(update_fields=["login_fail_count"])

    return user


def refresh_user_tokens(refresh_token):
    if not refresh_token:
        raise AuthenticationFailed("Refresh 토큰이 없습니다.")

    try:
        # JWT 디코딩을 통해 token_id를 가져옵니다.
        payload = jwt.decode(
            refresh_token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )
        token_id = payload["token_id"]

        # UUID를 사용해 토큰 객체를 찾습니다.
        token_obj = Token.objects.get(
            refresh_token_id=token_id,
            expires_at__gt=datetime.now(timezone.utc),
            is_blacklisted=False,
        )
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, Token.DoesNotExist):
        raise AuthenticationFailed("유효하지 않거나 만료된 Refresh 토큰입니다.")

    # 토큰 해시가 일치하는지 마지막으로 확인 (보안 강화)
    if not token_obj.check_refresh_token(refresh_token):
        raise AuthenticationFailed("유효하지 않거나 만료된 Refresh 토큰입니다.")

    user = token_obj.user

    # 기존 토큰 블랙리스트 처리
    token_obj.is_blacklisted = True
    token_obj.save()

    # 새로운 토큰 발급
    access_token, new_refresh_token, access_token_lifetime = generate_tokens(
        user, parent_token_id=token_obj.refresh_token_id
    )

    return access_token, new_refresh_token, access_token_lifetime, user
