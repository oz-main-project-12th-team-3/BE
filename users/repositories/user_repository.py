from datetime import datetime, timedelta, timezone

from django.conf import settings
from django.db import transaction

from ..exceptions import (
    AccountLockedException,
    UserNotFoundException,
)
from ..models import User, UserProfile

if not settings.IS_TEST_ENV:
    from django_otp.plugins.otp_totp.models import TOTPDevice


class UserRepository:
    def create_user(self, email, password, nickname=None, enable_2fa=False):
        """새로운 사용자를 생성하고 프로필을 연결합니다."""
        with transaction.atomic():
            user = User.objects.create_user(password=password, email=email)
            profile, created = UserProfile.objects.get_or_create(user=user)
            if nickname:
                profile.nickname = nickname
                profile.save()
            if not settings.IS_TEST_ENV and enable_2fa:
                TOTPDevice.objects.create(user=user, name="default", confirmed=False)
        return user

    def get_user_by_email(self, email):
        """이메일로 사용자를 조회합니다."""
        try:
            return User.objects.get(email=email)
        except User.DoesNotExist:
            raise UserNotFoundException("사용자를 찾을 수 없습니다.")

    def get_user_by_id(self, user_id):
        """ID로 사용자를 조회합니다."""
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise UserNotFoundException("사용자를 찾을 수 없습니다.")

    def update_user_password(self, user, new_password):
        """사용자 비밀번호를 업데이트하고 비밀번호 변경 시간을 기록합니다."""
        user.set_password(new_password)
        user.password_changed_at = datetime.now(timezone.utc)
        user.save()

    def update_login_fail_count(self, user, is_success):
        """로그인 실패 횟수를 업데이트합니다."""
        if is_success:
            user.login_fail_count = 0
            user.save(update_fields=["login_fail_count"])
        else:
            user.login_fail_count += 1
            if user.login_fail_count >= 5:
                user.account_locked_until = datetime.now(timezone.utc) + timedelta(
                    minutes=30
                )
            user.save(update_fields=["login_fail_count", "account_locked_until"])
            if user.is_account_locked():
                raise AccountLockedException(
                    "계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
                )

    def check_email_exists(self, email):
        """이메일이 이미 존재하는지 확인합니다."""
        return User.objects.filter(email=email).exists()

    def delete_user(self, user):
        """사용자를 삭제합니다."""
        user.delete()

    def get_user_profile(self, user):
        """사용자 프로필을 조회합니다."""
        try:
            return UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            return None

    if not settings.IS_TEST_ENV:

        def get_user_confirmed_2fa_device(self, user):
            """사용자의 확정된 2FA 기기를 조회합니다."""
            return TOTPDevice.objects.filter(user=user, confirmed=True).first()

        def get_user_unconfirmed_2fa_device(self, user):
            """사용자의 미확정 2FA 기기를 조회합니다."""
            return TOTPDevice.objects.filter(user=user, confirmed=False).first()

        def create_2fa_device(self, user):
            """새로운 2FA 기기를 생성합니다."""
            return TOTPDevice.objects.create(user=user, name="default")
