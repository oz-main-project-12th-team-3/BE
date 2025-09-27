import secrets
import string
import uuid

import pytest
from django.utils import timezone
from django_otp.oath import totp
from django_otp.plugins import otp_totp
from django_otp.util import hex_validator
from rest_framework.test import APIClient

from users.models import User, UserProfile
from users.repositories import token_repository, user_repository
from users.services import token_service, user_service


@pytest.fixture
def generate_password():
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"

    def _generate():
        while True:
            pwd = "".join(secrets.choice(alphabet) for _ in range(16))
            if (
                any(c.islower() for c in pwd)
                and any(c.isupper() for c in pwd)
                and any(c.isdigit() for c in pwd)
                and any(c in "!@#$%^&*()" for c in pwd)
                and len(pwd) >= 8
            ):
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
def token_service_fixture():
    ur = user_repository.UserRepository()
    tr = token_repository.TokenRepository()
    return token_service.TokenService(ur, tr)


@pytest.fixture
def user_service_fixture():
    ur = user_repository.UserRepository()
    tr = token_repository.TokenRepository()
    return user_service.UserService(ur, tr)


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


@pytest.mark.django_db
def test_authenticated_client_has_tokens(authenticated_client):
    client = authenticated_client
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies
