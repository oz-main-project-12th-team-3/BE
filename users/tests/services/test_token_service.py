import secrets
from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from users.exceptions import TokenAuthenticationFailed
from users.models import Token, User
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService


@pytest.fixture
def user(db):
    password = secrets.token_urlsafe(12)
    user = User.objects.create_user(email="jwt@example.com", password=password)
    if not user.password_changed_at:
        user.password_changed_at = timezone.now()
        user.save()
    return user


@pytest.fixture
def service(db):
    return TokenService(UserRepository(), TokenRepository())


@pytest.mark.django_db
def test_generate_tokens_and_temporary(user, service):
    access, refresh, lifetime = service.generate_tokens(user)
    assert isinstance(access, str)
    assert isinstance(refresh, str)
    assert lifetime == settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]

    temp_access, temp_refresh, temp_lifetime = service.generate_temporary_tokens(user)
    assert isinstance(temp_access, str)
    assert isinstance(temp_refresh, str)
    assert temp_lifetime.total_seconds() == 300  # 5분


@pytest.mark.django_db
def test_refresh_user_tokens_success(user, service):
    _, refresh, _ = service.generate_tokens(user)
    access2, refresh2, _, u = service.refresh_user_tokens(refresh)
    assert u == user
    assert isinstance(access2, str)
    assert isinstance(refresh2, str)


@pytest.mark.django_db
def test_refresh_user_tokens_no_token(user, service):
    with pytest.raises(TokenAuthenticationFailed):
        service.refresh_user_tokens(None)


@pytest.mark.django_db
def test_refresh_user_tokens_invalid_signature(service):
    bad_refresh = jwt.encode(
        {"user_id": 1}, "wrongkey", algorithm=settings.SIMPLE_JWT["ALGORITHM"]
    )
    with pytest.raises(TokenAuthenticationFailed):
        service.refresh_user_tokens(bad_refresh)


@pytest.mark.django_db
def test_refresh_user_tokens_mismatched_token(user, service):
    _, refresh, _ = service.generate_tokens(user)
    token_obj = Token.objects.first()
    token_obj.refresh_token_hash = "tampered"
    token_obj.save()
    with pytest.raises(TokenAuthenticationFailed):
        service.refresh_user_tokens(refresh)


@pytest.mark.django_db
def test_get_validated_payload_success_and_fail(service):
    now = timezone.now()
    payload = {
        "user_id": 1,
        "exp": now + timedelta(minutes=1),
    }
    token = jwt.encode(
        payload,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    result = service._get_validated_payload(token)
    assert result["user_id"] == 1

    expired_token = jwt.encode(
        {"user_id": 1, "exp": now - timedelta(seconds=1)},
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    with pytest.raises(TokenAuthenticationFailed):
        service._get_validated_payload(expired_token)

    invalid = token + "corrupted"
    with pytest.raises(TokenAuthenticationFailed):
        service._get_validated_payload(invalid)


@pytest.mark.django_db
def test_validate_user_and_password_time_cases(user, service):
    user.is_active = False
    user.save()
    with pytest.raises(TokenAuthenticationFailed):
        service._validate_user_and_password_time(user, {"pwd_changed_at": None})

    user.is_active = True
    user.save()

    ts = timezone.now()
    user.password_changed_at = ts
    user.save()
    wrong_payload = {"pwd_changed_at": (ts - timedelta(seconds=5)).isoformat()}
    with pytest.raises(TokenAuthenticationFailed):
        service._validate_user_and_password_time(user, wrong_payload)

    correct_payload = {"pwd_changed_at": ts.isoformat()}
    assert service._validate_user_and_password_time(user, correct_payload) is None


@pytest.mark.django_db
def test_is_valid_access_token_success(user, service):
    access, _, _ = service.generate_tokens(user)
    payload = service.is_valid_access_token(access)
    assert payload["user_id"] == user.id


@pytest.mark.django_db
def test_is_valid_access_token_no_user_id(service):
    token = jwt.encode(
        {"exp": timezone.now() + timedelta(minutes=1)},
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    with pytest.raises(TokenAuthenticationFailed):
        service.is_valid_access_token(token)


@pytest.mark.django_db
def test_is_valid_access_token_user_not_found(service):
    payload = {"user_id": 99999, "exp": timezone.now() + timedelta(minutes=1)}
    token = jwt.encode(
        payload,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    with pytest.raises(TokenAuthenticationFailed):
        service.is_valid_access_token(token)


@pytest.mark.django_db
def test_is_valid_access_token_password_time_mismatch(user, service):
    user.password_changed_at = timezone.now()
    user.save()
    payload = {
        "user_id": user.id,
        "exp": timezone.now() + timedelta(minutes=1),
        "pwd_changed_at": (
            user.password_changed_at - timedelta(seconds=10)
        ).isoformat(),
    }
    bad_token = jwt.encode(
        payload,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    with pytest.raises(TokenAuthenticationFailed):
        service.is_valid_access_token(bad_token)


@pytest.mark.django_db
def test_invalidate_refresh_token_success(user, service):
    _, refresh, _ = service.generate_tokens(user)
    token_obj = Token.objects.first()
    assert not token_obj.is_blacklisted
    service.invalidate_refresh_token(refresh)
    token_obj.refresh_from_db()
    assert token_obj.is_blacklisted


@pytest.mark.django_db
def test_invalidate_refresh_token_with_invalid_token(service):
    bad_token = "this.is.not.jwt"
    service.invalidate_refresh_token(bad_token)
    # 예외 없이 그냥 무시되며 DB 영향 없음
    assert Token.objects.count() == 0
