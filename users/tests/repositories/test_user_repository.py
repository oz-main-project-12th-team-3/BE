import secrets
from unittest.mock import patch

import pytest
from django.conf import settings

from users.exceptions import UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import UserRepository

# -----------------------------------------------------------
# TOTPDevice Mocking 설정
# -----------------------------------------------------------

# 실제 TOTPDevice 임포트 참조 (skipif 조건 설정용)
RealTOTPDevice = None
try:
    if not settings.IS_TEST_ENV:
        from django_otp.plugins.otp_totp.models import TOTPDevice as RealTOTPDevice
except ImportError:
    pass

# --- Mocking 클래스 정의 ---


class MockQuerySet:
    """filter의 반환값처럼 작동하는 최소한의 쿼리셋 Mock"""

    def __init__(self, objects=None):
        self._objects = objects if objects is not None else []

    def filter(self, *args, **kwargs):
        # NameError/Exception을 유발하는 쿼리셋 Mock이 필요하지 않은 경우, self 반환
        return self

    def first(self):
        return self._objects[0] if self._objects else None

    def delete(self):
        # NameError/Exception 테스트를 위해 이 메서드는 개별적으로 Mocking 됩니다.
        return len(self._objects), {}

    # 2FA delete_all_2fa_devices의 일반 Exception 커버를 위한 Mocking
    @classmethod
    def get_exception_raiser(cls, exception_to_raise):
        class ExceptionRaiser:
            def filter(self, *args, **kwargs):
                return self

            def delete(self):
                raise exception_to_raise

        return ExceptionRaiser()


class NameErrorMockManager:
    """TOTPDevice.objects를 대체하며, NameError를 유발합니다."""

    def create(self, *args, **kwargs):
        raise NameError("NameError forced on create")

    def filter(self, *args, **kwargs):
        # 필터링 시 NameError를 유발하는 쿼리셋을 반환하도록 설정
        class NameErrorRaiser:
            def first(self):
                # get_user_confirmed/unconfirmed_2fa_device 커버
                raise NameError("NameError forced on filter")

            def delete(self):
                # delete_all_2fa_devices 커버
                raise NameError("NameError forced on delete")

        return NameErrorRaiser()


class NameErrorRaisingClassMock:
    """NameErrorMockManager를 Manager로 사용하는 클래스 Mock"""

    objects = NameErrorMockManager()


# -----------------------------------------------------------
# Fixtures
# -----------------------------------------------------------


@pytest.fixture
def repo():
    """UserRepository 인스턴스를 반환합니다."""
    return UserRepository()


@pytest.fixture
def password():
    """안전한 임시 비밀번호를 반환합니다."""
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    """테스트용 일반 사용자를 생성합니다."""
    return User.objects.create_user(email="user@example.com", password=password)


# -----------------------------------------------------------
# 기본 CRUD 및 핵심 로직 테스트
# -----------------------------------------------------------


@pytest.mark.django_db
def test_create_user_no_2fa_no_nickname(repo, password):
    """닉네임 및 2FA 없이 사용자 생성 및 UserProfile 연결 확인."""
    email = "new1@example.com"
    user = repo.create_user(email=email, password=password)

    assert user.email == email
    assert user.check_password(password)

    # UserProfile이 생성되었고 user와 연결되었는지 확인
    profile = UserProfile.objects.get(user=user)
    assert profile is not None
    assert profile.nickname is None


@pytest.mark.django_db
def test_create_user_with_nickname(repo, password):
    """닉네임을 포함하여 사용자 생성 및 UserProfile 업데이트 확인."""
    nickname = "TesterNickname"
    user = repo.create_user(
        email="new2@example.com", password=password, nickname=nickname
    )
    assert UserProfile.objects.get(user=user).nickname == nickname


@pytest.mark.django_db
def test_create_user_with_2fa_nameerror(repo, password):
    """TOTPDevice 임포트 실패 시 사용자 생성 성공, 2FA 건너뛰는지 확인."""
    email = "totp_missing@example.com"

    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        user = repo.create_user(email=email, password=password, enable_2fa=True)

    assert user.email == email
    # UserProfile이 생성되었는지 확인
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_get_user_by_email_success_and_failure(repo, user):
    """이메일로 사용자 조회 성공 및 실패(UserNotFoundException) 테스트."""
    assert repo.get_user_by_email("user@example.com") == user
    with pytest.raises(UserNotFoundException) as excinfo:
        repo.get_user_by_email("nouser@example.com")
    assert "사용자를 찾을 수 없습니다." in str(excinfo.value)


@pytest.mark.django_db
def test_get_user_by_id_success_and_failure(repo, user):
    """ID로 사용자 조회 성공 및 실패(UserNotFoundException) 테스트."""
    assert repo.get_user_by_id(user.id) == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_id(999999)  # 존재하지 않는 ID


@pytest.mark.django_db
def test_update_user_password_sets_time(repo, user):
    """비밀번호 업데이트 및 password_changed_at 필드 업데이트 테스트."""
    new_pass = secrets.token_urlsafe(14)

    # set_password가 모델에서 오버라이딩되어 password_changed_at을 이미 설정했다고 가정
    old_time = user.password_changed_at
    assert old_time is not None

    # 비밀번호 업데이트 메서드 호출
    repo.update_user_password(user, new_pass)
    user.refresh_from_db()

    # 변경된 비밀번호와 시간 확인
    assert user.check_password(new_pass)
    # 시간이 업데이트되었는지 확인
    assert user.password_changed_at > old_time


@pytest.mark.django_db
def test_check_email_exists(repo, user):
    """이메일 존재 여부 확인 테스트."""
    assert repo.check_email_exists("user@example.com") is True
    assert repo.check_email_exists("no@example.com") is False


@pytest.mark.django_db
def test_delete_user(repo, user):
    """사용자 삭제 테스트."""
    user_id = user.id
    repo.delete_user(user)
    assert not User.objects.filter(id=user_id).exists()


@pytest.mark.django_db
def test_get_user_profile_success_and_none(repo, user):
    """사용자 프로필 조회 성공 및 실패(None 반환) 테스트."""
    # 1. 프로필이 있는 경우 (signal에 의해 생성됨)
    profile = repo.get_user_profile(user)
    assert isinstance(profile, UserProfile)

    # 2. 프로필이 없는 경우
    UserProfile.objects.filter(user=user).delete()  # 프로필 삭제
    assert repo.get_user_profile(user) is None


# -----------------------------------------------------------
# 2FA (TOTPDevice) - NameError/Exception 분기 커버
# -----------------------------------------------------------


@pytest.mark.django_db
def test_2fa_getters_and_creator_nameerror(repo, user):
    """2FA 조회/생성 메서드의 NameError 처리 테스트."""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        # 1. 미확정 장치 조회 (filter().first()에서 NameError)
        assert repo.get_user_unconfirmed_2fa_device(user) is None
        # 2. 확정 장치 조회 (filter().first()에서 NameError)
        assert repo.get_user_confirmed_2fa_device(user) is None
        # 3. 새로운 장치 생성 (create()에서 NameError)
        assert repo.create_2fa_device(user) is None


@pytest.mark.django_db
def test_delete_all_2fa_devices_nameerror(repo, user):
    """delete_all_2fa_devices의 NameError 처리 테스트."""
    with patch(
        "users.repositories.user_repository.TOTPDevice", new=NameErrorRaisingClassMock
    ):
        count = repo.delete_all_2fa_devices(user)
        # NameError 발생 시 0 반환
        assert count == 0


@pytest.mark.django_db
def test_delete_all_2fa_devices_exception(repo, user):
    """delete_all_2fa_devices의 일반 Exception 처리 테스트."""

    # 일반 Exception을 유발하는 MockManager 생성
    ExceptionRaiser = MockQuerySet.get_exception_raiser(
        Exception("Database error forced on delete")
    )

    with patch(
        "users.repositories.user_repository.TOTPDevice.objects", new=ExceptionRaiser
    ):
        count = repo.delete_all_2fa_devices(user)
        # 일반 Exception 발생 시 0 반환
        assert count == 0


# -----------------------------------------------------------
# 2FA (TOTPDevice) - 실제 객체 기반 성공 테스트
# -----------------------------------------------------------
@pytest.mark.skipif(
    RealTOTPDevice is None, reason="Requires real TOTPDevice to be imported"
)
@pytest.mark.django_db
def test_2fa_create_user_and_device_success(repo, password):
    """실제 TOTPDevice가 임포트된 경우의 create_user 및 장치 생성 테스트."""
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
    """실제 TOTPDevice가 임포트된 경우의 모든 2FA 메서드 성공 테스트."""

    # 1. 새로운 장치 생성
    new_device = repo.create_2fa_device(user)
    assert new_device is not None
    assert isinstance(new_device, RealTOTPDevice)
    new_device.confirmed = False
    new_device.name = "default_unconfirmed"
    new_device.save()

    # 2. 미확정 장치 조회
    assert repo.get_user_unconfirmed_2fa_device(user) == new_device
    assert repo.get_user_confirmed_2fa_device(user) is None

    # 3. 확정 장치 조회
    new_device.confirmed = True
    new_device.name = "default_confirmed"
    new_device.save()
    assert repo.get_user_confirmed_2fa_device(user) == new_device
    assert repo.get_user_unconfirmed_2fa_device(user) is None

    # 4. 모든 장치 삭제
    RealTOTPDevice.objects.create(user=user, name="another_device", confirmed=False)
    count = repo.delete_all_2fa_devices(user)
    assert count == 2
    assert RealTOTPDevice.objects.filter(user=user).count() == 0
