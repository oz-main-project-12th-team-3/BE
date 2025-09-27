from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from users.exceptions import TokenAuthenticationFailed


@pytest.mark.django_db
def test_generate_tokens_success(create_active_user, token_service_fixture):
    user, _ = create_active_user("normal_user")

    access_token, refresh_token, lifetime = token_service_fixture.generate_tokens(user)

    access_payload = jwt.decode(
        access_token,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert access_payload["user_id"] == user.id
    assert "exp" in access_payload
    assert "iat" in access_payload


@pytest.mark.django_db
def test_generate_tokens_with_none_password_changed(create_user, token_service_fixture):
    user, _ = create_user("nopwdchange")
    user.password_changed_at = None
    user.save()
    access_token, refresh_token, lifetime = token_service_fixture.generate_tokens(user)
    assert access_token and refresh_token


@pytest.mark.django_db
def test_refresh_user_tokens_with_expired_token(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("expired-refresh")

    original_decode = jwt.decode

    def raise_expired(*args, **kwargs):
        raise jwt.ExpiredSignatureError

    monkeypatch.setattr(jwt, "decode", raise_expired)

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.refresh_user_tokens("fake_refresh_token")

    monkeypatch.setattr(jwt, "decode", original_decode)


@pytest.mark.django_db
def test_refresh_user_tokens_with_invalid_token_id(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("invalidid")

    def raise_token_not_found(token_id):
        from users.exceptions import TokenNotFoundException

        raise TokenNotFoundException("토큰 없음")

    monkeypatch.setattr(
        token_service_fixture.token_repo, "get_valid_token_by_id", raise_token_not_found
    )

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.refresh_user_tokens("invalid_refresh_token")


@pytest.mark.django_db
def test_is_valid_access_token_inactive_user(create_active_user, token_service_fixture):
    user, _ = create_active_user("inactive_user")
    user.is_active = False
    user.save()

    access_token, _, _ = token_service_fixture.generate_tokens(user)
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(access_token)


@pytest.mark.django_db
def test_is_valid_access_token_pwd_changed_mismatch(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("pwd_change_mismatch")

    access_token, _, _ = token_service_fixture.generate_tokens(user)

    def fake_decode(token, key, algorithms):
        yesterday_iso = (timezone.now() - timezone.timedelta(days=1)).isoformat()
        return {
            "user_id": user.id,
            "pwd_changed_at": yesterday_iso,
        }

    monkeypatch.setattr(jwt, "decode", fake_decode)

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(access_token)


@pytest.mark.django_db
def test_generate_temporary_tokens(create_active_user, token_service_fixture):
    user, _ = create_active_user("temp_user")

    access_token, refresh_token, lifetime = (
        token_service_fixture.generate_temporary_tokens(user)
    )
    payload = jwt.decode(
        access_token,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
    )
    assert payload["user_id"] == user.id
    assert payload.get("is_temporary") is True
    assert lifetime == timedelta(minutes=5)


@pytest.mark.django_db
def test_refresh_user_tokens_success(create_active_user, token_service_fixture):
    user, _ = create_active_user("refresh_user")

    _, refresh_token, _ = token_service_fixture.generate_tokens(user)
    new_access, new_refresh, lifetime, refreshed_user = (
        token_service_fixture.refresh_user_tokens(refresh_token)
    )

    assert refreshed_user == user
    assert new_access is not None
    assert new_refresh is not None


@pytest.mark.django_db
def test_refresh_user_tokens_invalid(token_service_fixture):
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.refresh_user_tokens("invalid_token")


@pytest.mark.django_db
def test_is_valid_access_token_success(create_active_user, token_service_fixture):
    user, _ = create_active_user("valid_user")
    user.is_active = True
    user.save()

    access_token, _, _ = token_service_fixture.generate_tokens(user)
    payload = token_service_fixture.is_valid_access_token(access_token)
    assert payload["user_id"] == user.id


@pytest.mark.django_db
def test_is_valid_access_token_expired(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("expired_user")

    access_token, _, _ = token_service_fixture.generate_tokens(user)

    def fake_decode(*args, **kwargs):
        raise jwt.ExpiredSignatureError()

    monkeypatch.setattr(jwt, "decode", fake_decode)
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(access_token)


@pytest.mark.django_db
def test_is_valid_access_token_invalid_user(token_service_fixture):
    token = jwt.encode(
        {"invalid_field": 123},
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(token)


@pytest.mark.django_db
def test_invalidate_refresh_token_calls_blacklist(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("invalidate_call")

    access_token, refresh_token, _ = token_service_fixture.generate_tokens(user)

    called = {}

    def mock_blacklist(token_obj):
        called["called"] = True

    monkeypatch.setattr(
        token_service_fixture.token_repo, "blacklist_token", mock_blacklist
    )
    token_service_fixture.invalidate_refresh_token(refresh_token)
    assert called.get("called") is True

    token_service_fixture.invalidate_refresh_token("invalid_token")


@pytest.mark.django_db
def test_generate_tokens_with_parent_token(create_active_user, token_service_fixture):
    user, _ = create_active_user("parent_user")

    parent_access_token, parent_refresh_token, _ = (
        token_service_fixture.generate_tokens(user)
    )

    parent_token_obj = token_service_fixture.token_repo.get_valid_token_by_id(
        jwt.decode(
            parent_refresh_token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )["token_id"]
    )

    access_token, refresh_token, lifetime = token_service_fixture.generate_tokens(
        user, parent_token_id=parent_token_obj.refresh_token_id
    )
    assert access_token is not None
    assert refresh_token is not None
    assert lifetime.total_seconds() > 0


@pytest.mark.django_db
def test_refresh_user_tokens_blacklists_old_token(
    create_active_user, token_service_fixture, monkeypatch
):
    user, _ = create_active_user("blacklist_user")

    _, refresh_token, _ = token_service_fixture.generate_tokens(user)

    called = {}

    def mock_blacklist(token_obj):
        called["called"] = True

    monkeypatch.setattr(
        token_service_fixture.token_repo, "blacklist_token", mock_blacklist
    )

    new_access, new_refresh, lifetime, refreshed_user = (
        token_service_fixture.refresh_user_tokens(refresh_token)
    )
    assert called.get("called") is True
    assert refreshed_user.id == user.id


@pytest.mark.django_db
def test_is_valid_access_token_invalid_signature(token_service_fixture):
    invalid_token = jwt.encode({"user_id": 1}, "invalid_key", algorithm="HS256")
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(invalid_token)
