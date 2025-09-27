from datetime import timedelta

import pytest
from django.utils import timezone

from users.exceptions import PasswordMismatchException, UserNotFoundException
from users.models import UserProfile


@pytest.mark.django_db
class TestUserService:
    @pytest.fixture(autouse=True)
    def setup(
        self, user_service_fixture, create_user, create_2fa_device, generate_password
    ):
        self.user_service = user_service_fixture
        self.create_user = create_user
        self.create_2fa_device = create_2fa_device
        self.generate_password = generate_password

    def test_create_user_success(self):
        email = "test_create@example.com"
        password = self.generate_password()
        nickname = "Tester"
        user = self.user_service.create_user(
            email, password, nickname, enable_2fa=False
        )

        # UserService가 UserProfile 생성을 처리했는지 확인
        profile = UserProfile.objects.get(user=user)
        assert profile.nickname == nickname
        assert profile.enable_2fa is False  # 명시적 확인

    def test_create_user_duplicate_email(self):
        email = "dup@example.com"
        password = self.generate_password()
        self.user_service.create_user(email, password, "DupUser", enable_2fa=False)
        with pytest.raises(ValueError):
            self.user_service.create_user(email, password, "DupUser2", enable_2fa=False)

    def test_authenticate_user_success(self):
        email = "auth@example.com"
        password = self.generate_password()
        user, pwd = self.create_user(email, password)
        auth_user = self.user_service.authenticate_user(email, pwd)
        assert auth_user.id == user.id

    def test_authenticate_user_wrong_password(self):
        email = "wrongpwd@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)
        with pytest.raises(PasswordMismatchException):
            self.user_service.authenticate_user(email, "wrongpassword")

    def test_authenticate_user_inactive(self):
        email = "inactive@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)
        user.is_active = False
        user.save()
        with pytest.raises(ValueError):
            self.user_service.authenticate_user(email, password)

    def test_authenticate_user_locked_account(self):
        email = "locked_account@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)

        user.account_locked_until = timezone.now() + timedelta(hours=1)
        user.save()

        with pytest.raises(ValueError):
            self.user_service.authenticate_user(email, password)

    def test_login_with_optional_2fa_no_2fa(self):
        email = "no2fa@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)

        user_profile = user.user_profile
        user_profile.enable_2fa = False
        user_profile.save()

        result = self.user_service.login_with_optional_2fa(email, password)
        assert result[0].id == user.id
        assert result[1] is True  # 로그인 성공
        assert result[2] is False  # 2FA 대기 아님
        assert result[3] is None
        assert result[4] is None

    def test_login_with_optional_2fa_pending_and_confirmed(self):
        email = "2fa@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)

        user.user_profile.enable_2fa = True
        user.user_profile.save()

        device, get_token = self.create_2fa_device(user, confirmed=False)
        assert device is not None

        # 1. 2FA Pending 상태 확인
        result = self.user_service.login_with_optional_2fa(email, password)
        assert result[1] is False  # 로그인 토큰 반환 안됨
        assert result[2] is True  # 2FA 대기 상태

        # 2. 2FA 코드로 확인
        code = get_token()
        result_confirmed = self.user_service.login_with_optional_2fa(
            email, password, code
        )
        device.refresh_from_db()
        assert device.confirmed is True
        assert result_confirmed[1] is True  # 로그인 토큰 반환
        assert result_confirmed[2] is False  # 2FA 대기 아님

    def test_setup_2fa_and_confirm(self):
        email = "2fasetup@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)

        device, get_token = self.create_2fa_device(user, confirmed=False)
        token = get_token()

        for _ in range(3):
            if device.verify_token(token):
                break
            token = get_token()
        else:
            pytest.fail("2FA 토큰 검증 실패")

        assert self.user_service.confirm_2fa(user, token) is True

        confirmed_device = self.user_service.user_repo.get_user_confirmed_2fa_device(
            user
        )
        assert confirmed_device is not None and confirmed_device.confirmed is True

        new_token = get_token()
        verified_user = self.user_service.verify_2fa(email, new_token)
        assert verified_user.id == user.id

    def test_change_user_password(self):
        email = "changepwd@example.com"
        password_old = self.generate_password()
        password_new = self.generate_password()
        user, pwd = self.create_user(email, password_old)
        self.user_service.change_user_password(user, password_new)

        user.refresh_from_db()
        assert user.check_password(password_new) is True

    def test_delete_user_success(self):
        email = "delete@example.com"
        password = self.generate_password()
        user, pwd = self.create_user(email, password)
        res = self.user_service.delete_user(user, pwd)
        assert res is True
        with pytest.raises(UserNotFoundException):
            self.user_service.user_repo.get_user_by_email(email)

    def test_delete_user_wrong_password(self):
        email = "deletefail@example.com"
        password = self.generate_password()
        user, pwd = self.create_user(email, password)
        with pytest.raises(PasswordMismatchException):
            self.user_service.delete_user(user, "wrongpassword")

    def test_check_email_exists(self):
        email = "exist@example.com"
        password = self.generate_password()
        user, _ = self.create_user(email, password)
        assert self.user_service.check_email_exists(email) is True
        assert self.user_service.check_email_exists("nothis@user.com") is False
