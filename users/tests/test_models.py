from datetime import timedelta

import pytest
from django.utils import timezone

from users.models import Token, User
from users.tests.conftest import generate_random_password


@pytest.mark.django_db
def test_create_user_and_profile():
    email = "test@example.com"
    password = generate_random_password()
    user = User.objects.create_user(email, password)
    assert user.email == email
    assert user.is_active
    assert not user.is_staff
    assert not user.is_superuser
    assert user.user_profile is not None
    assert user.check_password(password)


@pytest.mark.django_db
def test_create_superuser():
    email = "super@example.com"
    password = generate_random_password()
    user = User.objects.create_superuser(email, password)
    assert user.email == email
    assert user.is_active
    assert user.is_staff
    assert user.is_superuser
    assert user.user_profile is not None  # ⚠️ 수정: user_profile로 접근
    assert user.check_password(password)


@pytest.mark.django_db
def test_is_account_locked_check(create_user):
    user, _ = create_user("locked@example.com")

    # User is not locked by default
    assert not user.is_account_locked()

    # To test the lock, manually set the locked until time
    # Set the lock time to a future date
    user.account_locked_until = timezone.now() + timedelta(minutes=10)
    user.save()

    # Now, the user should be locked
    assert user.is_account_locked()


@pytest.mark.django_db
def test_token_set_and_check(user_with_profile):
    user, _ = user_with_profile
    plain_token = "my-secret-refresh-token"

    # ⚠️ 수정: Token 객체를 직접 생성
    token_obj = Token(
        user=user,
        issued_at=timezone.now(),
        expires_at=timezone.now() + timedelta(days=7),
    )
    token_obj.set_refresh_token(plain_token)
    token_obj.save()

    # 올바른 토큰으로 확인
    assert token_obj.check_refresh_token(plain_token) is True
    # 잘못된 토큰으로 확인
    assert token_obj.check_refresh_token("wrong-token") is False
