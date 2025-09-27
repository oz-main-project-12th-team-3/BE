import secrets
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from users.models import Token, User, UserProfile


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    return User.objects.create_user(email="user@example.com", password=password)


@pytest.mark.django_db
def test_create_user_success():
    password = secrets.token_urlsafe(16)
    user = User.objects.create_user(email="user@example.com", password=password)
    assert user.email == "user@example.com"
    assert user.check_password(password)
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser


@pytest.mark.django_db
def test_create_user_without_email():
    with pytest.raises(ValueError):
        User.objects.create_user(email=None, password=secrets.token_urlsafe(8))


@pytest.mark.django_db
def test_create_superuser_success():
    password = secrets.token_urlsafe(12)
    superuser = User.objects.create_superuser(
        email="admin@example.com", password=password
    )
    assert superuser.is_staff
    assert superuser.is_superuser
    assert superuser.check_password(password)


@pytest.mark.django_db
def test_create_superuser_invalid_flags():
    password = secrets.token_urlsafe(12)
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="badstaff@example.com", password=password, is_staff=False
        )
    with pytest.raises(ValueError):
        User.objects.create_superuser(
            email="badsuper@example.com", password=password, is_superuser=False
        )


@pytest.mark.django_db
def test_user_str_and_account_lock():
    password = secrets.token_urlsafe(10)
    user = User.objects.create_user(email="lock@example.com", password=password)
    assert str(user) == "lock@example.com"
    assert not user.is_account_locked()

    user.account_locked_until = timezone.now() + timedelta(minutes=5)
    user.save()
    assert user.is_account_locked()


@pytest.mark.django_db
def test_token_set_and_check_refresh_token():
    user = User.objects.create_user(
        email="token@example.com", password=secrets.token_urlsafe(12)
    )
    token = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    refresh_plain = secrets.token_urlsafe(20)
    token.set_refresh_token(refresh_plain)
    token.save()

    assert token.check_refresh_token(refresh_plain)
    assert not token.check_refresh_token("wrongtoken")


@pytest.mark.django_db
def test_token_parent_child_relationship():
    user = User.objects.create_user(
        email="parent@example.com", password=secrets.token_urlsafe(12)
    )

    parent = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=5),
    )
    parent.set_refresh_token(secrets.token_urlsafe(25))
    parent.save()

    child = Token(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(hours=1),
        parent_token=parent,
    )
    child.set_refresh_token(secrets.token_urlsafe(25))  # 반드시 고유 토큰
    child.save()

    assert child.parent_token == parent
    assert parent.child_tokens.first() == child


@pytest.mark.django_db
def test_user_profile_auto_created_signal():
    user = User.objects.create_user(
        email="signal@example.com", password=secrets.token_urlsafe(12)
    )
    assert hasattr(user, "user_profile")
    assert user.user_profile is not None


@pytest.mark.django_db
def test_user_profile_update_fields():
    user = User.objects.create_user(
        email="profile@example.com", password=secrets.token_urlsafe(12)
    )
    profile = user.user_profile
    profile.nickname = "Tester"
    profile.profile_image_url = "http://test.com/img.png"
    profile.save()

    refreshed = UserProfile.objects.get(user=user)
    assert refreshed.nickname == "Tester"
    assert refreshed.profile_image_url.startswith("http")


@pytest.mark.django_db
def test_token_unique_refresh_token_hash_constraint():
    user = User.objects.create_user(
        email="unique@example.com", password=secrets.token_urlsafe(12)
    )
    token1 = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    plain1 = secrets.token_urlsafe(24)
    token1.set_refresh_token(plain1)
    token1.save()

    token2 = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    plain2 = secrets.token_urlsafe(25)  # 반드시 다른 문자열로 생성해야 중복 안됨
    token2.set_refresh_token(plain2)
    token2.save()


@pytest.mark.django_db
def test_token_unique_refresh_token_hash_constraint_violation():
    user = User.objects.create_user(
        email="repeat@example.com", password=secrets.token_urlsafe(12)
    )
    plain = secrets.token_urlsafe(24)

    token1 = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    token1.set_refresh_token(plain)
    token1.save()

    token2 = Token.objects.create(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=1),
    )
    token2.set_refresh_token(plain)  # 의도적으로 중복 값 넣기

    with pytest.raises(IntegrityError):
        token2.save()
