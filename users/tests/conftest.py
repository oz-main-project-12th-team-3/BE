import secrets
import string
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins import otp_totp
from django_otp.util import hex_validator
from rest_framework.test import APIClient

from users.models import (
    Token,
    User,
    UserProfile,
)
from users.repositories import token_repository, user_repository
from users.services import token_service, user_service


class FlexiMock(MagicMock):
    """
    MagicMock을 상속받아 딕셔너리처럼 .get()과 [] 접근을 지원하는 Mock 객체.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, spec_set=dict, **kwargs)
        # .get('key', default) 구문 지원
        self.get = lambda x, default=None: getattr(self, x, default)
        # ['key'] 구문 지원
        self.__getitem__.side_effect = lambda key: getattr(self, key)


def _is_strong_password(pwd: str) -> bool:
    """비밀번호가 모든 필수 요소를 포함하는지 확인합니다."""
    return (
        len(pwd) >= 8
        and any(c.islower() for c in pwd)
        and any(c.isupper() for c in pwd)
        and any(c.isdigit() for c in pwd)
        and any(c in "!@#$%^&*()" for c in pwd)
    )


@pytest.fixture
def generate_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"

    def _generate():
        while True:
            pwd = "".join(secrets.choice(alphabet) for _ in range(16))
            if _is_strong_password(pwd):
                return pwd

    return _generate


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user(db, generate_password):
    def _create(email, password=None, nickname=None):
        if password is None:
            password = generate_password()
        user = User.objects.create_user(email=email, password=password)
        now = timezone.now()
        if timezone.is_naive(now):
            now = timezone.make_aware(now)
        user.password_changed_at = now
        user.save()
        UserProfile.objects.get_or_create(
            user=user, defaults={"nickname": nickname or "tester"}
        )
        return user, password

    return _create


@pytest.fixture
def create_active_user(create_user):
    """password_changed_at이 현재 시간으로 설정된 활성 사용자 객체를 생성합니다."""

    def _create(email_prefix):
        user, password = create_user(f"{email_prefix}@{uuid.uuid4().hex}.com")
        # create_user 픽스처는 이미 password_changed_at을 설정하므로 추가 로직 불필요
        return user, password

    return _create


@pytest.fixture
def token_service_fixture():
    ur = user_repository.UserRepository()
    tr = token_repository.TokenRepository()
    return token_service.TokenService(ur, tr)


@pytest.fixture
def user_service_fixture(token_service_fixture):
    ur = user_repository.UserRepository()
    tr = token_repository.TokenRepository()
    return user_service.UserService(ur, tr, token_service_fixture)


@pytest.fixture
def authenticated_client(api_client, create_user, token_service_fixture):
    user, pwd = create_user(f"user_{uuid.uuid4().hex}@example.com")
    now = timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now)
    user.password_changed_at = now
    user.save()
    access_token, refresh_token, _ = token_service_fixture.generate_tokens(user)
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user)

    client.user = user
    client.password = pwd  # 비밀번호 변경/삭제 테스트를 위해 비밀번호도 저장
    return client


@pytest.fixture
def create_2fa_device():
    def _create(user, confirmed=False):
        device = otp_totp.models.TOTPDevice.objects.create(
            user=user, name="default", confirmed=confirmed
        )

        def get_token():
            key = device.bin_key
            if not hex_validator(key):
                raise ValueError("Invalid bin key")
            return f"{totp(key):06d}"

        return device, get_token

    return _create


@pytest.fixture
def create_test_token(db):
    def _create(
        user, expires_in_days=1, is_blacklisted=False, refresh_token_plain=None
    ):
        issued_at = timezone.now()
        expires_at = issued_at + timedelta(days=expires_in_days)

        # Naive datetime 객체를 Aware하게 만드는 로직은 그대로 유지
        if timezone.is_naive(issued_at):
            issued_at = timezone.make_aware(issued_at)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)

        token_obj = Token.objects.create(
            user=user,
            refresh_token_id=uuid.uuid4(),
            issued_at=issued_at,
            expires_at=expires_at,
            is_blacklisted=is_blacklisted,
        )

        plain_token = refresh_token_plain if refresh_token_plain else str(uuid.uuid4())
        token_obj.set_refresh_token(plain_token)
        token_obj.save()

        return token_obj

    return _create


@pytest.mark.django_db
def test_authenticated_client_has_tokens(authenticated_client):
    client = authenticated_client
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies
