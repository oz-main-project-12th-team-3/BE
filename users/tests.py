import hashlib
import secrets
import string
from datetime import timedelta
from unittest.mock import patch

import jwt
import pytest
from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.test import APIClient

from users.admin import TokenAdmin, UserAdmin, UserProfileAdmin
from users.models import Token, User, UserProfile
from users.serializers import (
    PasswordChangeSerializer,
    UserSerializer,
)
from users.services import user_service, token_service
from users.authentication import JWTAuthentication


# --- Helper Functions ---
def generate_random_password(length=12):
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


# --- Fixtures ---
@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def create_user_fixture():
    def _create_user(email, password=None, **extra_fields):
        if password is None:
            password = generate_random_password()
        # Use the service layer to create user
        user = user_service.create_user(email=email, password=password, nickname=email.split('@')[0], **extra_fields)
        return user, password

    return _create_user


@pytest.fixture
def user_with_profile(create_user_fixture):
    user, password = create_user_fixture(email="testuser@example.com")
    return user, password


@pytest.fixture
def user_with_tokens(user_with_profile):
    user, password = user_with_profile
    access_token, refresh_token = token_service.generate_tokens(user)
    token_service.record_refresh_token(user, refresh_token)
    return user, access_token, refresh_token, password


@pytest.fixture
def authenticated_client(api_client, user_with_tokens):
    user, access_token, refresh_token, _ = user_with_tokens
    client = api_client
    client.cookies["access_token"] = access_token
    client.cookies["refresh_token"] = refresh_token
    client.force_authenticate(user=user)
    return client


# --- Test Models ---
@pytest.mark.django_db
def test_create_user_and_profile(create_user_fixture):
    user, _ = create_user_fixture("newuser@example.com")
    assert user.email == "newuser@example.com"
    assert user.is_active
    assert user.role == "user"
    assert UserProfile.objects.filter(user=user).exists()


# --- Test Services ---
@pytest.mark.django_db
def test_authenticate_user_valid(create_user_fixture):
    user, password = create_user_fixture("authuser@example.com")
    authenticated_user = user_service.authenticate_user(user.email, password)
    assert authenticated_user.email == user.email
    assert authenticated_user.login_fail_count == 0


@pytest.mark.django_db
def test_authenticate_user_account_locked(create_user_fixture):
    user, password = create_user_fixture("locked@example.com")
    user.account_locked_until = timezone.now() + timedelta(minutes=30)
    user.save()
    try:
        user_service.authenticate_user(user.email, password)
        pytest.fail("PermissionDenied가 발생해야 합니다.")
    except PermissionDenied as e:
        assert "계정이 잠겼습니다" in str(e)


@pytest.mark.django_db
def test_generate_tokens_with_password_changed(user_with_profile):
    user, _ = user_with_profile
    user.password_changed_at = timezone.now()
    user.save()
    access_token, _ = token_service.generate_tokens(user)
    decoded = jwt.decode(
        access_token,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert "pwd_changed_at" in decoded
    assert decoded["pwd_changed_at"] == user.password_changed_at.isoformat()


# --- Test Views ---
@pytest.mark.django_db
def test_user_register_view(api_client):
    url = reverse("user-signup")
    data = {
        "email": "newuser@test.com",
        "password": generate_random_password(),
        "nickname": "nick123",
    }
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert UserProfile.objects.get(user__email=data["email"]).nickname == "nick123"


@pytest.mark.django_db
def test_user_login_view(api_client, user_with_profile):
    user, password = user_with_profile
    url = reverse("user-login")
    data = {"email": user.email, "password": password}
    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.data
    assert "refresh_token" in response.cookies


@pytest.mark.django_db
def test_jwt_authentication_password_changed(user_with_profile):
    user, _ = user_with_profile
    auth = JWTAuthentication()
    access_token, _ = token_service.generate_tokens(user)
    # Simulate password change
    user.password_changed_at = timezone.now()
    user.save()
    
    request = type(
        "Request",
        (object,),
        {"headers": {"Authorization": f"Bearer {access_token}"}, "COOKIES": {}},
    )
    with pytest.raises(
        AuthenticationFailed, match="비밀번호가 변경되어 토큰이 무효화되었습니다."
    ):
        auth.authenticate(request)


@pytest.mark.django_db
def test_logout_view(authenticated_client):
    url = reverse("user-logout")
    response = authenticated_client.post(url)
    assert response.status_code == status.HTTP_200_OK
    assert response.cookies["refresh_token"].value == ""


@pytest.mark.django_db
def test_password_change_view(authenticated_client, user_with_tokens):
    user, _, _, old_password = user_with_tokens
    url = reverse("my-password-change") # Use new URL name
    new_password = generate_random_password()
    data = {"current_password": old_password, "new_password": new_password}
    response = authenticated_client.post(url, data, format="json") # Use POST
    assert response.status_code == status.HTTP_200_OK
    assert "다시 로그인해주세요" in response.data["detail"]


@pytest.mark.django_db
def test_token_refresh_view(api_client, user_with_tokens):
    _, _, refresh_token, _ = user_with_tokens
    url = reverse("token-refresh")
    api_client.cookies["refresh_token"] = refresh_token
    response = api_client.post(url, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert "access_token" in response.data


@pytest.mark.django_db
def test_check_email_view(api_client, user_with_profile):
    user, _ = user_with_profile
    url = reverse("check-email")
    # Test existing email
    response = api_client.post(url, {"email": user.email}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["available"] is False
    # Test available email
    response = api_client.post(url, {"email": "available@test.com"}, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["available"] is True