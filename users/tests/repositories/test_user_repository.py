import secrets
from unittest.mock import patch

import pytest
from django.conf import settings
from django.utils import timezone as django_timezone

from users.exceptions import AccountLockedException, UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import (
    ACCOUNT_LOCK_DURATION_MINUTES,
    LOGIN_FAILURE_LIMIT,
    UserRepository,
)

# -----------------------------------------------------------
# TOTPDevice 모의(Mock) 설정 및 NameError/Exception 유발 클래스
# -----------------------------------------------------------

# 실제 TOTPDevice가 임포트될 경우를 대비한 별칭 정의
RealTOTPDevice = None
try:
    if not settings.IS_TEST_ENV:
        from django_otp.plugins.otp_totp.models import TOTPDevice as RealTOTPDevice
except ImportError:
    pass


class NameErrorRaisingQuerySetMock:
    """filter()의 반환값처럼 행동하며, delete() 시 NameError를 던집니다."""

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        # first() 호출 시 NameError가 발생하지 않도록 None 반환 (repository 로직에 따름)
        return None

    def delete(self):
        raise NameError("NameError forced on delete on queryset")


class ExceptionRaisingQuerySetMock:
    """일반 Exception을 던져서 delete_all_2fa_devices의 마지막 except 분기."""

    def filter(self, *args, **kwargs):
        return self

    def delete(self):
        raise Exception("Database error forced on delete")


class NameErrorMockManager:
    """Manager 객체처럼 행동하며, 호출 시 NameError를 던지거나 유발 객체 반환."""

    def create(self, *args, **kwargs):
        raise NameError("NameError forced on create")

    def filter(self, *args, **kwargs):
        # filter는 쿼리셋을 반환해야 하므로, NameError를 던지는 Mock을 반환
        return NameErrorRaisingQuerySetMock()


class ExceptionMockManager:
    """Manager 객체처럼 행동하며, Exception을 유발하는 쿼리셋 Mock을 반환합니다."""

    def create(self, *args, **kwargs):
        # create_2fa_device NameError 분기는 NameErrorMockManager로 충분히 커버됨
        return None

    def filter(self, *args, **kwargs):
        return ExceptionRaisingQuerySetMock()


class NameErrorRaisingClassMock:
    """
    TOTPDevice를 대체하며, NameError를 유발하는 객체를 반환하도록 설정하는 클래스.
    """

    objects = NameErrorMockManager()


class ExceptionRaisingClassMock:
    """
    TOTPDevice를 대체하며, Exception을 유발하는 쿼리셋 Mock을 반환하는 클래스.
    """

    objects = ExceptionMockManager()


@pytest.fixture
def repo():
    return UserRepository()


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="user@example.com")
    user.set_password(password)
    user.save()
    return user


# -----------------------------------------------------------
# 기존 테스트 및 누락 부분 추가 테스트
# -----------------------------------------------------------


@pytest.mark.django_db
def test_create_user_no_2fa_no_nickname(repo, password):
    email = "new1@example.com"
    user = repo.create_user(email=email, password=password)
    assert user.email == email
    assert user.check_password(password)
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_user_with_nickname(repo, password):
    user = repo.create_user(
        email="new2@example.com", password=password, nickname="Tester"
    )
    assert UserProfile.objects.get(user=user).nickname == "Tester"


@pytest.mark.django_db
def test_create_user_with_2fa_nameerror(repo, password):
    """
    create_user의 try...except NameError 블록이 실행 확인
    """
    # NameError를 던지는 Mock 클래스 사용
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        email = "totp_missing@example.com"
        # NameError 발생, except NameError 블록으로 pass 처리되어, 사용자 생성은 성공
        user = repo.create_user(email=email, password=password, enable_2fa=True)
        assert user.email == email


@pytest.mark.django_db
def test_get_user_by_email_success_and_failure(repo, user):
    assert repo.get_user_by_email("user@example.com") == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_email("nouser@example.com")


@pytest.mark.django_db
def test_get_user_by_id_success_and_failure(repo, user):
    assert repo.get_user_by_id(user.id) == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_id(999999)


@pytest.mark.django_db
def test_update_user_password_sets_time(repo, user, password):
    new_pass = secrets.token_urlsafe(14)
    old_time = django_timezone.now() - django_timezone.timedelta(days=1)
    user.password_changed_at = old_time
    user.save()
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
    repo.delete_user(user)
    assert not User.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_get_user_profile(repo, user):
    profile = repo.get_user_profile(user)
    assert isinstance(profile, UserProfile)
    UserProfile.objects.filter(user=user).delete()
    assert repo.get_user_profile(user) is None


# -----------------------------------------------------------
# 로그인 실패/잠금 로직 (Login Fail Count)
# -----------------------------------------------------------


@pytest.mark.django_db
def test_update_login_fail_count_success(repo, user):
    """로그인 성공 시 실패 횟수 초기화 및 잠금 해제"""
    user.login_fail_count = 3
    user.account_locked_until = django_timezone.now() - django_timezone.timedelta(
        minutes=1
    )
    user.save()
    repo.update_login_fail_count(user, is_success=True)
    user.refresh_from_db()
    assert user.login_fail_count == 0
    assert user.account_locked_until is None


@pytest.mark.django_db
def test_update_login_fail_count_success_already_zero(repo, user):
    """로그인 성공 시 실패 횟수가 이미 0일 때 저장 로직을 타지 않음"""
    user.login_fail_count = 0
    user.account_locked_until = None
    user.save()

    with patch.object(user, "save") as mock_save:
        repo.update_login_fail_count(user, is_success=True)
        # 0에서 0으로 업데이트하는 경우 save() 호출 안 함
        mock_save.assert_not_called()


@pytest.mark.django_db
def test_update_login_fail_count_failure_no_lock(repo, user):
    user.login_fail_count = 0
    user.save()
    for _ in range(LOGIN_FAILURE_LIMIT - 1):  # 4번 실패 (잠금 미만)
        repo.update_login_fail_count(user, is_success=False)
    user.refresh_from_db()
    assert user.login_fail_count == LOGIN_FAILURE_LIMIT - 1
    assert user.account_locked_until is None


@pytest.mark.django_db
def test_update_login_fail_count_failure_with_lock(repo, user):
    user.login_fail_count = LOGIN_FAILURE_LIMIT - 1
    user.save()
    with pytest.raises(AccountLockedException):
        repo.update_login_fail_count(user, is_success=False)
    user.refresh_from_db()
    assert user.login_fail_count == LOGIN_FAILURE_LIMIT
    assert user.account_locked_until > django_timezone.now()


@pytest.mark.django_db
def test_update_login_fail_count_lock_expired_then_success(repo, user):
    """잠금 시간이 만료된 후 로그인 성공 시 잠금 해제"""
    user.login_fail_count = LOGIN_FAILURE_LIMIT
    user.account_locked_until = django_timezone.now() - django_timezone.timedelta(
        minutes=10
    )
    user.save()

    repo.update_login_fail_count(user, is_success=True)

    user.refresh_from_db()
    assert user.login_fail_count == 0
    assert user.account_locked_until is None


@pytest.mark.django_db
def test_update_login_fail_count_already_locked_before_check(repo, user):
    """잠금 상태에서 로그인 시도 시 예외 발생 확인"""
    # is_account_locked()가 True를 반환하도록 설정
    mock_now = django_timezone.now()
    lock_until = mock_now + django_timezone.timedelta(minutes=10)
    user.account_locked_until = lock_until
    user.save()

    with pytest.raises(AccountLockedException) as excinfo:
        # is_success가 True든 False든 AccountLockedException이 먼저 발생
        repo.update_login_fail_count(user, is_success=True)

    expected_message = (
        f"계정이 {ACCOUNT_LOCK_DURATION_MINUTES}분 동안 잠금 처리되었습니다."
    )
    assert expected_message in str(excinfo.value)


# -----------------------------------------------------------
# 2FA (TOTPDevice) - 성공 및 NameError/Exception 분기 커버
# -----------------------------------------------------------


@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_2fa_create_user_and_device_success(repo, password):
    """실제 TOTPDevice가 임포트된 경우의 create_user 테스트"""
    email = "2fa_new@example.com"
    new_user = repo.create_user(email=email, password=password, enable_2fa=True)
    device = RealTOTPDevice.objects.filter(user=new_user).first()
    assert device is not None
    assert device.confirmed is False


@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_2fa_getters_and_creator_success(repo, user):
    """실제 TOTPDevice가 임포트된 경우의 모든 2FA 메서드 테스트"""

    # 1. 미확정 장치 조회
    unconfirmed_dev = RealTOTPDevice.objects.create(
        user=user, name="d1", confirmed=False
    )
    assert repo.get_user_unconfirmed_2fa_device(user) == unconfirmed_dev
    assert repo.get_user_confirmed_2fa_device(user) is None

    # 2. 확정 장치 조회
    unconfirmed_dev.delete()
    confirmed_dev = RealTOTPDevice.objects.create(user=user, name="d2", confirmed=True)
    assert repo.get_user_confirmed_2fa_device(user) == confirmed_dev
    assert repo.get_user_unconfirmed_2fa_device(user) is None

    # 3. 새로운 장치 생성
    confirmed_dev.delete()
    new_device = repo.create_2fa_device(user)
    assert new_device is not None
    assert isinstance(new_device, RealTOTPDevice)


@pytest.mark.django_db
def test_get_user_unconfirmed_2fa_device_nameerror(repo, user):
    """get_user_unconfirmed_2fa_device의 NameError 처리 테스트"""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        assert repo.get_user_unconfirmed_2fa_device(user) is None


@pytest.mark.django_db
def test_get_user_confirmed_2fa_device_nameerror(repo, user):
    """get_user_confirmed_2fa_device의 NameError 처리 테스트"""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        assert repo.get_user_confirmed_2fa_device(user) is None


@pytest.mark.django_db
def test_create_2fa_device_nameerror(repo, user):
    """create_2fa_device의 NameError 처리 테스트"""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        assert repo.create_2fa_device(user) is None


@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_delete_all_2fa_devices_success(repo, user):
    """실제 TOTPDevice가 있을 때의 정상 삭제 테스트"""
    RealTOTPDevice.objects.create(user=user, name="d1")
    RealTOTPDevice.objects.create(user=user, name="d2")
    count = repo.delete_all_2fa_devices(user)
    assert count == 2
    assert RealTOTPDevice.objects.filter(user=user).count() == 0


@pytest.mark.django_db
def test_delete_all_2fa_devices_nameerror(repo, user):
    """delete_all_2fa_devices의 NameError 처리 테스트"""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        count = repo.delete_all_2fa_devices(user)
        # NameError 발생 시 0 반환
        assert count == 0


@pytest.mark.django_db
def test_delete_all_2fa_devices_exception(repo, user):
    """delete_all_2fa_devices의 일반 Exception 처리 테스트"""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=ExceptionRaisingClassMock
    ):
        count = repo.delete_all_2fa_devices(user)
        # 일반 Exception 발생 시 0 반환
        assert count == 0
