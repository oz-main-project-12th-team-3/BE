from datetime import datetime

import pytest
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from users.exceptions import AccountLockedException, UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import UserRepository


@pytest.mark.django_db(transaction=True)
class TestUserRepository:
    @pytest.fixture(autouse=True)
    def setup(self, generate_password):
        self.repo = UserRepository()
        self.user = User.objects.create_user(
            email="commonuser@example.com", password=generate_password()
        )

    def test_create_user_profile_and_2fa(self, generate_password):
        pw = generate_password()
        user = self.repo.create_user(
            "user@example.com", pw, nickname="tester", enable_2fa=True
        )
        assert user.email == "user@example.com"

        profile = UserProfile.objects.get(user=user)
        assert profile.nickname == "tester"

        device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
        assert device is not None

    def test_get_user_by_email_success_and_not_found(self):
        found = self.repo.get_user_by_email(self.user.email)
        assert found.pk == self.user.pk

        with pytest.raises(UserNotFoundException):
            self.repo.get_user_by_email("notexists@example.com")

    def test_get_user_by_id_success_and_not_found(self):
        found = self.repo.get_user_by_id(self.user.id)
        assert found.email == self.user.email

        with pytest.raises(UserNotFoundException):
            self.repo.get_user_by_id(99999)

    def test_update_user_password_sets_time_and_password(self, generate_password):
        user = self.user
        new_pw = generate_password()
        self.repo.update_user_password(user, new_pw)

        user.refresh_from_db()
        now = timezone.now()

        assert user.password_changed_at is not None
        changed_at = user.password_changed_at or timezone.make_aware(datetime.min)
        assert changed_at <= now
        assert user.check_password(new_pw)

    def test_update_login_fail_count_success_and_trigger_lock(self, generate_password):
        user = User.objects.create_user(
            email="failcount@example.com", password=generate_password()
        )
        user.login_fail_count = 3
        user.account_locked_until = None
        user.save(update_fields=["login_fail_count", "account_locked_until"])

        self.repo.update_login_fail_count(user, is_success=True)
        user.refresh_from_db()
        assert user.login_fail_count == 0

        user.login_fail_count = 4
        user.account_locked_until = None
        user.save(update_fields=["login_fail_count", "account_locked_until"])

        with pytest.raises(AccountLockedException):
            self.repo.update_login_fail_count(user, is_success=False)

        user.refresh_from_db()
        assert user.login_fail_count == 5
        assert user.account_locked_until > timezone.now()
        assert user.is_account_locked()

    def test_check_email_exists_true_and_false(self):
        assert self.repo.check_email_exists(self.user.email) is True
        assert self.repo.check_email_exists("absent@example.com") is False

    def test_delete_user_removes_user(self):
        user = self.user
        self.repo.delete_user(user)
        with pytest.raises(User.DoesNotExist):
            User.objects.get(pk=user.pk)

    def test_get_user_profile_returns_none_or_profile(self):
        user = self.user
        profile = self.repo.get_user_profile(user)
        assert profile.user == user

        profile.delete()
        assert self.repo.get_user_profile(user) is None

    def test_get_user_confirmed_and_unconfirmed_2fa_devices(self):
        user = self.user
        confirmed_device = TOTPDevice.objects.create(
            user=user, name="default", confirmed=True
        )
        unconfirmed_device = TOTPDevice.objects.create(
            user=user, name="temp", confirmed=False
        )

        assert self.repo.get_user_confirmed_2fa_device(user) == confirmed_device
        assert self.repo.get_user_unconfirmed_2fa_device(user) == unconfirmed_device

    def test_create_2fa_device_creates_unconfirmed_device(self):
        user = self.user
        TOTPDevice.objects.filter(user=user).delete()

        device = self.repo.create_2fa_device(user)
        assert device.user == user
        assert device.name == "default"
        assert device.confirmed is False
