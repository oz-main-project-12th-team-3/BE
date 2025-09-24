from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from users.models import Token
from users.services.token_service import (
    generate_tokens,
    invalidate_refresh_token,
    is_valid_access_token,
    refresh_user_tokens,
)


@pytest.mark.django_db
def test_generate_tokens_success(user_with_profile):
    user, _ = user_with_profile
    access_token, refresh_token, _ = generate_tokens(user)
    assert isinstance(access_token, str)
    assert isinstance(refresh_token, str)
    assert Token.objects.filter(user=user, is_blacklisted=False).exists()


@pytest.mark.django_db
def test_refresh_user_tokens_success(user_with_tokens):
    user, original_access_token, refresh_token, _ = user_with_tokens
    new_access_token, new_refresh_token, new_lifetime, refreshed_user = (
        refresh_user_tokens(refresh_token)
    )
    assert new_access_token is not None
    assert new_refresh_token is not None
    assert new_access_token != original_access_token
    assert new_refresh_token != refresh_token
    assert refreshed_user.id == user.id


@pytest.mark.django_db
def test_refresh_user_tokens_invalid_refresh_token():
    with pytest.raises(AuthenticationFailed):
        refresh_user_tokens("invalid_token")


@pytest.mark.django_db
def test_refresh_user_tokens_blacklisted_token(user_with_tokens):
    user, _, refresh_token, _ = user_with_tokens
    invalidate_refresh_token(refresh_token)
    with pytest.raises(AuthenticationFailed):
        refresh_user_tokens(refresh_token)


@pytest.mark.django_db
def test_is_valid_access_token_success(user_with_tokens):
    user, access_token, _, _ = user_with_tokens
    is_valid, payload = is_valid_access_token(access_token)
    assert is_valid
    assert payload["user_id"] == user.id


@pytest.mark.django_db
def test_is_valid_access_token_expired(user_with_profile):
    user, _ = user_with_profile
    payload = {
        "user_id": user.id,
        "exp": timezone.now() - timedelta(seconds=1),
        "iat": timezone.now() - timedelta(minutes=1),
        "pwd_changed_at": None,
    }
    expired_token = jwt.encode(
        payload, settings.SIMPLE_JWT["SIGNING_KEY"], algorithm="HS256"
    )
    is_valid, _ = is_valid_access_token(expired_token)
    assert not is_valid


@pytest.mark.django_db
def test_is_valid_access_token_invalid():
    is_valid, _ = is_valid_access_token("invalid.token.string")
    assert not is_valid


@pytest.mark.django_db
def test_invalidate_refresh_token(user_with_tokens):
    user, _, refresh_token, _ = user_with_tokens
    invalidate_refresh_token(refresh_token)
    token_obj = Token.objects.get(user=user)
    assert token_obj.is_blacklisted is True


@pytest.mark.django_db
def test_invalidate_refresh_token_non_existent():
    invalidate_refresh_token("invalid_or_non_existent_token")
    assert True
