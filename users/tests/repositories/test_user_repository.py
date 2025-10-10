import secrets
from unittest.mock import patch

import pytest
from django.conf import settings

from users.exceptions import UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import UserRepository

# 실제 TOTPDevice import (2FA 정상 테스트용)
RealTOTPDevice = None
try:
    if not settings.IS_TEST_ENV:
        from django_otp.plugins.otp_totp.models import TOTPDevice as RealTOTPDevice
except ImportError:
    pass


class MockQuerySet:
    def __init__(self, objects=None):
        self._objects = objects or []

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._objects[0] if self._objects else None

    def delete(self):
        return len(self._objects), {}

    @classmethod
    def get_exception_raiser(cls, exception_to_raise):
        class ExceptionRaiser:
            def filter(self, *args, **kwargs):
                return self

            def delete(self):
                raise exception_to_raise

        return ExceptionRaiser()


class NameErrorMockManager:
    def create(self, *args, **kwargs):
        raise NameError("NameError forced on create")

    def filter(self, *args, **kwargs):
        class NameErrorRaiser:
            def first(self):
                raise NameError("NameError forced on filter")

            def delete(self):
                raise NameError("NameError forced on delete")

        return NameErrorRaiser()


class NameErrorRaisingClassMock:
    objects = NameErrorMockManager()


@pytest.fixture
def repo():
    return UserRepository()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    return User.objects.create_user(email="user@example.com", password=password)


@pytest.mark.django_db
def test_create_user_no_2fa_no_nickname(repo, password):
    email = "new1@example.com"
    user = repo.create_user(email=email, password=password)
    assert user.email == email
    assert user.check_password(password)
    profile = UserProfile.objects.get(user=user)
    assert profile.nickname is None


@pytest.mark.django_db
def test_create_user_with_nickname(repo, password):
    nickname = "TesterNickname"
    user = repo.create_user(
        email="new2@example.com", password=password, nickname=nickname
    )
    assert UserProfile.objects.get(user=user).nickname == nickname


@pytest.mark.django_db
def test_create_user_with_2fa_nameerror(repo, password):
    email = "totp_missing@example.com"
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        user = repo.create_user(email=email, password=password, enable_2fa=True)
    assert user.email == email
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_get_user_by_email_success_and_failure(repo, user):
    assert repo.get_user_by_email("user@example.com") == user
    with pytest.raises(UserNotFoundException) as e:
        repo.get_user_by_email("nouser@example.com")
    assert "사용자를 찾을 수 없습니다." in str(e.value)


@pytest.mark.django_db
def test_get_user_by_id_success_and_failure(repo, user):
    assert repo.get_user_by_id(user.id) == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_id(999999)


@pytest.mark.django_db
def test_update_user_password_sets_time(repo, user):
    new_pass = secrets.token_urlsafe(14)
    old_time = user.password_changed_at
    repo.update_user_password(user, new_pass)
    user.refresh_from_db()
    assert user.check_password(new_pass)
    assert user.password_changed_at > old_time


@pytest.mark.django_db
def test_check_email_exists(repo, user):
    assert repo.check_email_exists("user@example.com") is True
    assert repo.check_email_exists("no@example.com") is False


@pytest.mark.django_db
def test_delete_user(repo, user):
    user_id = user.id
    repo.delete_user(user)
    assert not User.objects.filter(id=user_id).exists()


@pytest.mark.django_db
def test_get_user_profile_success_and_none(repo, user):
    profile = repo.get_user_profile(user)
    assert isinstance(profile, UserProfile)
    UserProfile.objects.filter(user=user).delete()
    assert repo.get_user_profile(user) is None


@pytest.mark.django_db
def test_2fa_getters_and_creator_nameerror(repo, user):
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        assert repo.get_user_unconfirmed_2fa_device(user) is None
        assert repo.get_user_confirmed_2fa_device(user) is None
        assert repo.create_2fa_device(user) is None


@pytest.mark.django_db
def test_delete_all_2fa_devices_nameerror(repo, user):
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        count = repo.delete_all_2fa_devices(user)
        assert count == 0


@pytest.mark.django_db
def test_delete_all_2fa_devices_exception(repo, user):
    ExceptionRaiser = MockQuerySet.get_exception_raiser(
        Exception("Database error forced on delete")
    )
    with patch(
        "users.repositories.user_repository.TOTPDevice.objects", new=ExceptionRaiser
    ):
        count = repo.delete_all_2fa_devices(user)
        assert count == 0


@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_2fa_create_user_and_device_success(repo, password):
    email = "2fa_new@example.com"
    new_user = repo.create_user(email=email, password=password, enable_2fa=True)
    device = RealTOTPDevice.objects.filter(user=new_user).first()
    assert device is not None
    assert device.confirmed is False


@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_2fa_getters_creator_and_deleter_success(repo, user):
    new_device = repo.create_2fa_device(user)
    assert new_device is not None
    assert isinstance(new_device, RealTOTPDevice)
    new_device.confirmed = False
    new_device.name = "default_unconfirmed"
    new_device.save()

    assert repo.get_user_unconfirmed_2fa_device(user) == new_device
    assert repo.get_user_confirmed_2fa_device(user) is None

    new_device.confirmed = True
    new_device.name = "default_confirmed"
    new_device.save()
    assert repo.get_user_confirmed_2fa_device(user) == new_device
    assert repo.get_user_unconfirmed_2fa_device(user) is None

    RealTOTPDevice.objects.create(user=user, name="another_device", confirmed=False)
    count = repo.delete_all_2fa_devices(user)
    assert count == 2
    assert RealTOTPDevice.objects.filter(user=user).count() == 0
