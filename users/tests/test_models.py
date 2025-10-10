import secrets
import uuid
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from users.models import Token, User, UserProfile


@pytest.fixture
def password():
    return secrets.token_urlsafe(16)


@pytest.fixture
def user(db, password):
    return User.objects.create_user(email="user@example.com", password=password)


@pytest.mark.django_db
def test_create_user_and_initial_state(user, password):
    assert user.email == "user@example.com"
    assert user.check_password(password)
    assert user.is_active is True
    assert not user.is_staff
    assert not user.is_superuser
    assert user.password_changed_at is not None
    assert str(user) == "user@example.com"


@pytest.mark.django_db
def test_create_user_without_email_raises_value_error():
    with pytest.raises(ValueError, match="이메일은 필수 입력 항목입니다."):
        User.objects.create_user(email=None, password=secrets.token_urlsafe(8))


@pytest.mark.django_db
def test_create_superuser_success(password):
    superuser = User.objects.create_superuser(
        email="admin@example.com", password=password
    )
    assert superuser.is_staff and superuser.is_superuser


@pytest.mark.django_db
def test_create_superuser_invalid_flags_raises_value_error(password):
    with pytest.raises(ValueError, match="is_staff=True여야 합니다."):
        User.objects.create_superuser(
            email="badstaff@example.com", password=password, is_staff=False
        )
    with pytest.raises(ValueError, match="is_superuser=True여야 합니다."):
        User.objects.create_superuser(
            email="badsuper@example.com", password=password, is_superuser=False
        )


@pytest.mark.django_db
def test_user_set_password_updates_changed_at(user):
    initial_time = user.password_changed_at
    new_pass = secrets.token_urlsafe(12)

    user.set_password(new_pass)
    user.save()
    user.refresh_from_db()

    assert user.password_changed_at > initial_time
    assert user.check_password(new_pass)


@pytest.mark.django_db
def test_token_initial_fields_and_defaults(user):
    issued_at = timezone.now() - timedelta(minutes=5)
    expires_at = timezone.now() + timedelta(days=7)
    token = Token.objects.create(user=user, issued_at=issued_at, expires_at=expires_at)

    assert token.refresh_token_hash == ""
    assert not token.is_blacklisted
    assert token.parent_token is None
    assert token.user == user
    assert isinstance(token.refresh_token_id, uuid.UUID)


@pytest.mark.django_db
def test_token_set_and_check_refresh_token(user):
    token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    refresh_plain = secrets.token_urlsafe(32)
    token.set_refresh_token(refresh_plain)
    token.save()

    assert len(token.refresh_token_hash) == 64
    assert token.check_refresh_token(refresh_plain)
    assert not token.check_refresh_token(secrets.token_urlsafe(32))


@pytest.mark.django_db
def test_token_unique_refresh_token_hash_constraint(user):
    plain = secrets.token_urlsafe(32)
    token1 = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    token1.set_refresh_token(plain)
    token1.save()

    token2 = Token(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    token2.set_refresh_token(plain)

    with pytest.raises(IntegrityError):
        token2.save()


@pytest.mark.django_db
def test_token_parent_child_rotation_relationship(user):
    parent = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
    )
    parent.set_refresh_token(secrets.token_urlsafe(32))
    parent.save()

    child = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
        parent_token=parent,
    )

    assert parent.child_tokens.first() == child
    assert child.parent_token == parent

    parent.delete()
    child.refresh_from_db()
    assert child.parent_token is None


@pytest.mark.django_db
def test_token_expiration_status(user):
    now = timezone.now()
    issued_at = now - timedelta(hours=1)

    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now + timedelta(days=1),
    )
    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now - timedelta(days=1),
    )
    Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=issued_at,
        expires_at=now + timedelta(seconds=1),
    )

    expired_tokens = Token.objects.filter(expires_at__lt=now)
    active_tokens = Token.objects.filter(expires_at__gte=now)

    assert expired_tokens.count() == 1
    assert active_tokens.count() == 2

    for token in expired_tokens:
        reloaded = Token.objects.get(pk=token.pk)
        assert reloaded.is_expired

    for token in active_tokens:
        reloaded = Token.objects.get(pk=token.pk)
        assert not reloaded.is_expired


@pytest.mark.django_db
def test_user_profile_auto_created_signal(user):
    assert hasattr(user, "user_profile")
    assert user.user_profile is not None
    assert user.user_profile.user == user


@pytest.mark.django_db
def test_user_profile_fields_and_update(user):
    profile = user.user_profile

    assert profile.nickname is None
    assert profile.profile_image_url is None

    new_nick = "ProTester"
    new_url = "https://new.image.com/pro.jpg"

    profile.nickname = new_nick
    profile.profile_image_url = new_url
    profile.last_login = timezone.now()
    profile.save()

    refreshed = UserProfile.objects.get(user=user)
    assert refreshed.nickname == new_nick
    assert refreshed.profile_image_url == new_url
    assert refreshed.last_login is not None


@pytest.mark.django_db
def test_user_str_method(user):
    assert str(user) == user.email


@pytest.mark.django_db
def test_token_is_expired_property(user):
    now = timezone.now()

    # 만료 토큰
    token_expired = Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    assert token_expired.is_expired is True

    # 유효 토큰
    token_valid = Token.objects.create(
        user=user,
        refresh_token_hash=secrets.token_hex(16),
        issued_at=now - timedelta(hours=1),
        expires_at=now + timedelta(days=1),
    )
    assert token_valid.is_expired is False
