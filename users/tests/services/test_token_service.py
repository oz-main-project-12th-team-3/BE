from datetime import timedelta

import jwt
import pytest
from django.conf import settings
from django.utils import timezone

from users.exceptions import TokenAuthenticationFailed


@pytest.mark.django_db
def test_generate_tokens_success(create_user, token_service_fixture):
    user, _ = create_user("normal_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

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
    user, _ = create_user("nopwdchange@example.com")
    user.password_changed_at = None
    user.save()
    access_token, refresh_token, lifetime = token_service_fixture.generate_tokens(user)
    assert access_token and refresh_token


@pytest.mark.django_db
def test_refresh_user_tokens_with_expired_token(
    create_user, token_service_fixture, monkeypatch
):
    user, _ = create_user("expired-refresh@example.com")
    user.password_changed_at = timezone.now()
    user.save()

    original_decode = jwt.decode

    def raise_expired(*args, **kwargs):
        raise jwt.ExpiredSignatureError

    monkeypatch.setattr(jwt, "decode", raise_expired)

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.refresh_user_tokens("fake_refresh_token")

    monkeypatch.setattr(jwt, "decode", original_decode)


@pytest.mark.django_db
def test_refresh_user_tokens_with_invalid_token_id(
    create_user, token_service_fixture, monkeypatch
):
    user, _ = create_user("invalidid@example.com")
    user.password_changed_at = timezone.now()
    user.save()

    # 토큰 repo의 get_valid_token_by_id가 TokenNotFoundException 발생하도록 mock
    def raise_token_not_found(token_id):
        from users.exceptions import TokenNotFoundException

        raise TokenNotFoundException("토큰 없음")

    monkeypatch.setattr(
        token_service_fixture.token_repo, "get_valid_token_by_id", raise_token_not_found
    )

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.refresh_user_tokens("invalid_refresh_token")


@pytest.mark.django_db
def test_is_valid_access_token_inactive_user(create_user, token_service_fixture):
    user, _ = create_user("inactive_user@example.com")
    user.is_active = False
    user.password_changed_at = timezone.now()
    user.save()

    access_token, _, _ = token_service_fixture.generate_tokens(user)
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(access_token)


@pytest.mark.django_db
def test_is_valid_access_token_pwd_changed_mismatch(
    create_user, token_service_fixture, monkeypatch
):
    user, _ = create_user("pwd_change_mismatch@example.com")
    user.password_changed_at = timezone.now()
    user.save()

    access_token, _, _ = token_service_fixture.generate_tokens(user)

    # monkeypatch jwt.decode to return different pwd_changed_at
    def fake_decode(token, key, algorithms):
        return {
            "user_id": user.id,
            "pwd_changed_at": (timezone.now() - timezone.timedelta(days=1)).isoformat(),
        }

    monkeypatch.setattr(jwt, "decode", fake_decode)

    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(access_token)


@pytest.mark.django_db
def test_generate_temporary_tokens(create_user, token_service_fixture):
    user, _ = create_user("temp_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

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
def test_refresh_user_tokens_success(create_user, token_service_fixture):
    user, _ = create_user("refresh_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

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
def test_is_valid_access_token_success(create_user, token_service_fixture):
    user, _ = create_user("valid_user@example.com")
    user.is_active = True
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

    access_token, _, _ = token_service_fixture.generate_tokens(user)
    payload = token_service_fixture.is_valid_access_token(access_token)
    assert payload["user_id"] == user.id


@pytest.mark.django_db
def test_is_valid_access_token_expired(create_user, token_service_fixture, monkeypatch):
    user, _ = create_user("expired_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

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
def test_invalidate_refresh_token(create_user, token_service_fixture):
    user, _ = create_user("invalidate_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

    _, refresh_token, _ = token_service_fixture.generate_tokens(user)

    # mock blacklist_token 함수로 호출 검증
    called = {}

    original_blacklist_token = token_service_fixture.token_repo.blacklist_token

    def mock_blacklist_token(token_obj):
        called["called"] = True

    token_service_fixture.token_repo.blacklist_token = mock_blacklist_token
    token_service_fixture.invalidate_refresh_token(refresh_token)
    assert called.get("called") is True

    # 유효하지 않은 토큰 블랙리스트 처리 시도 (예외 발생 X)
    token_service_fixture.invalidate_refresh_token("invalid_token")

    # 원래 함수로 복원
    token_service_fixture.token_repo.blacklist_token = original_blacklist_token


@pytest.mark.django_db
def test_generate_tokens_with_parent_token(create_user, token_service_fixture):
    user, _ = create_user("parent_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

    # 부모 토큰 생성
    parent_access_token, parent_refresh_token, _ = (
        token_service_fixture.generate_tokens(user)
    )

    # 부모 토큰 객체 취득
    parent_token_obj = token_service_fixture.token_repo.get_valid_token_by_id(
        jwt.decode(
            parent_refresh_token,
            settings.SIMPLE_JWT["SIGNING_KEY"],
            algorithms=[settings.SIMPLE_JWT["ALGORITHM"]],
        )["token_id"]
    )

    # 부모 토큰의 refresh_token_id를 parent_token_id로 전달하여 자식 토큰 생성
    access_token, refresh_token, lifetime = token_service_fixture.generate_tokens(
        user, parent_token_id=parent_token_obj.refresh_token_id
    )
    assert access_token is not None
    assert refresh_token is not None
    assert lifetime.total_seconds() > 0


@pytest.mark.django_db
def test_refresh_user_tokens_blacklists_old_token(create_user, token_service_fixture):
    user, _ = create_user("blacklist_user@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

    _, refresh_token, _ = token_service_fixture.generate_tokens(user)

    called = {}

    # 기존 blacklist_token 메서드 백업
    original_blacklist_token = token_service_fixture.token_repo.blacklist_token

    # mock blacklist_token 정의
    def mock_blacklist_token(token_obj):
        called["called"] = True

    token_service_fixture.token_repo.blacklist_token = mock_blacklist_token

    new_access, new_refresh, lifetime, refreshed_user = (
        token_service_fixture.refresh_user_tokens(refresh_token)
    )
    assert called.get("called") is True
    assert refreshed_user.id == user.id

    # 원상복구
    token_service_fixture.token_repo.blacklist_token = original_blacklist_token


@pytest.mark.django_db
def test_is_valid_access_token_invalid_signature(token_service_fixture):
    invalid_token = jwt.encode({"user_id": 1}, "invalid_key", algorithm="HS256")
    with pytest.raises(TokenAuthenticationFailed):
        token_service_fixture.is_valid_access_token(invalid_token)


@pytest.mark.django_db
def test_invalidate_refresh_token_calls_blacklist(create_user, token_service_fixture):
    user, _ = create_user("invalidate_refresh@example.com")
    user.password_changed_at = timezone.now()
    if timezone.is_naive(user.password_changed_at):
        user.password_changed_at = timezone.make_aware(user.password_changed_at)
    user.save()

    _, refresh_token, _ = token_service_fixture.generate_tokens(user)

    called = {}

    original_blacklist = token_service_fixture.token_repo.blacklist_token

    def mock_blacklist(token_obj):
        called["yes"] = True

    token_service_fixture.token_repo.blacklist_token = mock_blacklist
    token_service_fixture.invalidate_refresh_token(refresh_token)
    assert called.get("yes") is True

    # invalid token should not raise
    token_service_fixture.invalidate_refresh_token("invalid_token")

    token_service_fixture.token_repo.blacklist_token = original_blacklist


@pytest.mark.django_db
def test_invalidate_refresh_token_blacklist_called(
    create_user, token_service_fixture, monkeypatch
):
    user, _ = create_user("invalidate_call@example.com")
    user.password_changed_at = timezone.now()
    user.save()

    access_token, refresh_token, _ = token_service_fixture.generate_tokens(user)

    called = {}

    def mock_blacklist(token_obj):
        called["called"] = True

    monkeypatch.setattr(
        token_service_fixture.token_repo, "blacklist_token", mock_blacklist
    )
    token_service_fixture.invalidate_refresh_token(refresh_token)
    assert called.get("called") is True

    # invalid token should not raise error
    token_service_fixture.invalidate_refresh_token("invalid_token")
