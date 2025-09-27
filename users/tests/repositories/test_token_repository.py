import secrets
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from users.exceptions import TokenBlacklistedException, TokenNotFoundException
from users.models import User
from users.repositories.token_repository import TokenRepository


@pytest.fixture
def user(db):
    """토큰 테스트용 사용자 생성 (비밀번호는 secrets 랜덤 사용)"""
    password = secrets.token_urlsafe(16)
    return User.objects.create_user(email="test@example.com", password=password)


@pytest.mark.django_db
def test_create_token_with_naive_datetime(user):
    repo = TokenRepository()
    refresh_token_id = uuid.uuid4()
    refresh_token_plain = secrets.token_urlsafe(32)

    issued_at = timezone.now().replace(tzinfo=None)  # naive datetime
    expires_at = timezone.now().replace(tzinfo=None) + timedelta(days=1)

    token = repo.create_token(
        user=user,
        refresh_token_id=refresh_token_id,
        refresh_token_plain=refresh_token_plain,
        issued_at=issued_at,
        expires_at=expires_at,
    )

    assert token.refresh_token_id == refresh_token_id
    assert token.check_refresh_token(refresh_token_plain)
    assert token.issued_at.tzinfo is not None
    assert token.expires_at.tzinfo is not None


@pytest.mark.django_db
def test_get_valid_token_by_id_success(user):
    repo = TokenRepository()
    refresh_token_id = uuid.uuid4()
    refresh_token_plain = secrets.token_urlsafe(24)

    created = repo.create_token(
        user=user,
        refresh_token_id=refresh_token_id,
        refresh_token_plain=refresh_token_plain,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
    )

    result = repo.get_valid_token_by_id(refresh_token_id)
    assert result == created


@pytest.mark.django_db
def test_get_valid_token_by_id_expired(user):
    repo = TokenRepository()
    refresh_token_id = uuid.uuid4()
    plain = secrets.token_urlsafe(24)

    _ = repo.create_token(
        user=user,
        refresh_token_id=refresh_token_id,
        refresh_token_plain=plain,
        issued_at=timezone.now() - timedelta(days=1),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    with pytest.raises(TokenBlacklistedException) as e:
        repo.get_valid_token_by_id(refresh_token_id)
    assert "만료된 Refresh 토큰" in str(e.value)


@pytest.mark.django_db
def test_get_valid_token_by_id_not_found(user):
    repo = TokenRepository()
    fake_id = uuid.uuid4()

    with pytest.raises(TokenNotFoundException) as e:
        repo.get_valid_token_by_id(fake_id)
    assert "유효하지 않거나 만료된 Refresh 토큰" in str(e.value)


@pytest.mark.django_db
def test_blacklist_token(user):
    repo = TokenRepository()
    plain = secrets.token_urlsafe(24)

    token = repo.create_token(
        user=user,
        refresh_token_id=uuid.uuid4(),
        refresh_token_plain=plain,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )

    assert token.is_blacklisted is False
    repo.blacklist_token(token)
    token.refresh_from_db()
    assert token.is_blacklisted is True


@pytest.mark.django_db
def test_blacklist_all_user_tokens(user):
    repo = TokenRepository()

    t1 = repo.create_token(
        user=user,
        refresh_token_id=uuid.uuid4(),
        refresh_token_plain=secrets.token_urlsafe(20),
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    t2 = repo.create_token(
        user=user,
        refresh_token_id=uuid.uuid4(),
        refresh_token_plain=secrets.token_urlsafe(20),
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=2),
    )
    assert t1.is_blacklisted is False
    assert t2.is_blacklisted is False

    repo.blacklist_all_user_tokens(user)
    t1.refresh_from_db()
    t2.refresh_from_db()
    assert t1.is_blacklisted
    assert t2.is_blacklisted
