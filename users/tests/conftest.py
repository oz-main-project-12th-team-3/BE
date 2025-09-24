import secrets
import string

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from users.models import User, UserProfile
from users.services.token_service import generate_tokens


def generate_random_password(length=12):
    """숫자, 대문자, 소문자, 특수문자가 포함된 안전한 랜덤 비밀번호를 생성합니다."""
    characters = string.ascii_letters + string.digits + string.punctuation
    while True:
        password = "".join(secrets.choice(characters) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in string.punctuation for c in password)
        ):
            return password


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user(db):
    def _create_user(email, password=None, **extra_fields):
        if password is None:
            password = generate_random_password()

        user_fields = {
            k: extra_fields.pop(k)
            for k in [
                "is_active",
                "is_staff",
                "is_superuser",
                "two_factor_enabled",
                "password_changed_at",
            ]
            if k in extra_fields
        }

        user = User.objects.create_user(email=email, password=password, **user_fields)

        if "nickname" in extra_fields:
            # UserProfile이 이미 create_user에서 생성되었을 수 있으므로 get_or_create 사용
            profile, created = UserProfile.objects.get_or_create(user=user)
            profile.nickname = extra_fields["nickname"]
            profile.save()

        return user, password

    return _create_user


@pytest.fixture
def user_with_profile(create_user):
    """기본 유저와 프로필, 비밀번호를 반환하는 픽스처"""
    password = generate_random_password()
    user, _ = create_user(email="testuser@example.com", password=password)
    return user, password


@pytest.fixture
def user_with_tokens(db, create_user):
    """토큰을 가진 유저, 비밀번호, 그리고 토큰 쌍을 반환하는 픽스처"""
    password = generate_random_password()
    user, _ = create_user(email="tokenuser@example.com", password=password)

    user.password_changed_at = timezone.now()
    user.save()

    access_token, refresh_token, lifetime = generate_tokens(user)
    return user, access_token, refresh_token, password


@pytest.fixture
def authenticated_client(api_client, user_with_tokens):
    """토큰으로 인증된 APIClient 객체를 반환하는 픽스처"""
    user, access_token, refresh_token, _ = user_with_tokens
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def admin_user(create_user):
    """관리자 권한을 가진 유저와 비밀번호를 반환하는 픽스처"""
    password = generate_random_password()
    user, _ = create_user(
        email="admin@example.com",
        password=password,
        is_staff=True,
        is_superuser=True,
    )
    return user, password
