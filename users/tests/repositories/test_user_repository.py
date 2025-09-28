import secrets
from datetime import datetime

import pytest
from django.conf import settings

from users.exceptions import AccountLockedException, UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import UserRepository

if not settings.IS_TEST_ENV:
    from django_otp.plugins.otp_totp.models import TOTPDevice


@pytest.fixture
def user(db):
    password = secrets.token_urlsafe(12)
    return User.objects.create_user(email="user@example.com", password=password)


@pytest.mark.skipif(
    settings.IS_TEST_ENV, reason="2FA tests disabled in CI/Test environment"
)
@pytest.mark.django_db
def test_create_user_with_profile_and_nickname_and_2fa():
    repo = UserRepository()
    password = secrets.token_urlsafe(10)
    user = repo.create_user(
        email="new@example.com",
        password=password,
        nickname="Tester",
        enable_2fa=True,
    )
    assert UserProfile.objects.get(user=user).nickname == "Tester"
    device = TOTPDevice.objects.filter(user=user).first()
    assert device is not None
    assert device.confirmed is False


@pytest.mark.django_db
def test_get_user_by_email_success_and_failure(user):
    repo = UserRepository()
    found = repo.get_user_by_email("user@example.com")
    assert found == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_email("nouser@example.com")


@pytest.mark.django_db
def test_get_user_by_id_success_and_failure(user):
    repo = UserRepository()
    found = repo.get_user_by_id(user.id)
    assert found == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_id(999999)


@pytest.mark.django_db
def test_update_user_password_sets_time(user):
    repo = UserRepository()
    new_pass = secrets.token_urlsafe(14)
    repo.update_user_password(user, new_pass)
    user.refresh_from_db()
    assert user.check_password(new_pass)
    assert isinstance(user.password_changed_at, datetime)


@pytest.mark.django_db
def test_update_login_fail_count_success_and_failure(user):
    repo = UserRepository()

    # 성공 로그인 → 실패 횟수 초기화
    user.login_fail_count = 3
    user.save()
    repo.update_login_fail_count(user, is_success=True)
    user.refresh_from_db()
    assert user.login_fail_count == 0

    # 실패 로그인 누적
    for i in range(5):
        if i < 4:
            repo.update_login_fail_count(user, is_success=False)
        else:
            with pytest.raises(AccountLockedException):
                repo.update_login_fail_count(user, is_success=False)
    user.refresh_from_db()
    assert user.is_account_locked()


@pytest.mark.django_db
def test_check_email_exists(user):
    repo = UserRepository()
    assert repo.check_email_exists("user@example.com") is True
    assert repo.check_email_exists("no@example.com") is False


@pytest.mark.django_db
def test_delete_user(user):
    repo = UserRepository()
    repo.delete_user(user)
    assert not User.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_get_user_profile(user):
    repo = UserRepository()
    profile = repo.get_user_profile(user)
    assert isinstance(profile, UserProfile)

    # 삭제해서 없는 경우 → None 반환
    UserProfile.objects.filter(user=user).delete()
    assert repo.get_user_profile(user) is None


@pytest.mark.skipif(
    settings.IS_TEST_ENV, reason="2FA tests disabled in CI/Test environment"
)
@pytest.mark.django_db
def test_get_user_confirmed_unconfirmed_2fa(user):
    repo = UserRepository()
    # unconfirmed 디바이스 생성
    dev = TOTPDevice.objects.create(user=user, name="d1", confirmed=False)
    assert repo.get_user_unconfirmed_2fa_device(user) == dev
    assert repo.get_user_confirmed_2fa_device(user) is None

    # confirmed 디바이스 생성
    dev.confirmed = True
    dev.save()
    assert repo.get_user_confirmed_2fa_device(user) == dev


@pytest.mark.skipif(
    settings.IS_TEST_ENV, reason="2FA tests disabled in CI/Test environment"
)
@pytest.mark.django_db
def test_create_2fa_device(user):
    repo = UserRepository()
    device = repo.create_2fa_device(user)
    assert isinstance(device, TOTPDevice)
    assert device.user == user
