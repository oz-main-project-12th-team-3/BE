import secrets

import pytest
from django.conf import settings
from django.utils import timezone as django_timezone

from users.exceptions import AccountLockedException, UserNotFoundException
from users.models import User, UserProfile
from users.repositories.user_repository import UserRepository

# 2FA 관련 클래스가 임포트되었는지 확인합니다.
try:
    if not settings.IS_TEST_ENV:
        from django_otp.plugins.otp_totp.models import TOTPDevice
    else:
        # 테스트 환경에서 NameError를 모방하기 위해 임시 더미를 만듭니다.
        # 실제 NameError는 파일 상단의 'if' 블록으로 인해 발생합니다.
        class TOTPDevice:
            pass
except ImportError:

    class TOTPDevice:
        pass


@pytest.fixture
def repo():
    """UserRepository 인스턴스"""
    return UserRepository()


@pytest.fixture
def password():
    """랜덤 비밀번호 생성"""
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    """테스트용 활성 사용자 생성 및 비밀번호 설정"""
    user = User.objects.create_user(email="user@example.com")
    user.set_password(password)
    user.save()
    return user


# ----------------------------------------------------------------------
# 1. User CRUD & Profile Tests
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_create_user_no_2fa_no_nickname(repo, password):
    """2FA 비활성화 및 닉네임 없이 사용자 생성"""
    email = "new1@example.com"
    user = repo.create_user(email=email, password=password)
    assert user.email == email
    assert user.check_password(password)
    assert UserProfile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_create_user_with_nickname(repo, password):
    """닉네임 설정 확인"""
    user = repo.create_user(
        email="new2@example.com", password=password, nickname="Tester"
    )
    assert UserProfile.objects.get(user=user).nickname == "Tester"


@pytest.mark.django_db
def test_get_user_by_email_success_and_failure(repo, user):
    """이메일 조회 성공 및 실패 테스트"""
    found = repo.get_user_by_email("user@example.com")
    assert found == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_email("nouser@example.com")


@pytest.mark.django_db
def test_get_user_by_id_success_and_failure(repo, user):
    """ID 조회 성공 및 실패 테스트"""
    found = repo.get_user_by_id(user.id)
    assert found == user
    with pytest.raises(UserNotFoundException):
        repo.get_user_by_id(999999)


@pytest.mark.django_db
def test_update_user_password_sets_time(repo, user, password):
    """비밀번호 업데이트 및 변경 시간 기록 테스트"""
    new_pass = secrets.token_urlsafe(14)
    old_time = django_timezone.now() - django_timezone.timedelta(days=1)
    user.password_changed_at = old_time
    user.save()

    repo.update_user_password(user, new_pass)
    user.refresh_from_db()
    assert user.check_password(new_pass)
    # password_changed_at이 업데이트되었는지 확인
    assert user.password_changed_at > old_time


@pytest.mark.django_db
def test_check_email_exists(repo, user):
    """이메일 존재 여부 확인 테스트"""
    assert repo.check_email_exists("user@example.com") is True
    assert repo.check_email_exists("no@example.com") is False


@pytest.mark.django_db
def test_delete_user(repo, user):
    """사용자 삭제 테스트"""
    repo.delete_user(user)
    assert not User.objects.filter(id=user.id).exists()


@pytest.mark.django_db
def test_get_user_profile(repo, user):
    """사용자 프로필 조회 테스트 (존재/부재)"""
    # 1. 존재
    profile = repo.get_user_profile(user)
    assert isinstance(profile, UserProfile)

    # 2. 부재 (None 반환 분기 커버)
    UserProfile.objects.filter(user=user).delete()
    assert repo.get_user_profile(user) is None


# ----------------------------------------------------------------------
# 2. Login Failure Count & Lock Tests
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_update_login_fail_count_success(repo, user):
    """로그인 성공 시 실패 횟수 초기화 테스트"""
    user.login_fail_count = 3
    user.save()
    repo.update_login_fail_count(user, is_success=True)
    user.refresh_from_db()
    assert user.login_fail_count == 0
    assert user.account_locked_until is None


@pytest.mark.django_db
def test_update_login_fail_count_failure_no_lock(repo, user):
    """로그인 실패 시 횟수 증가 (잠금 임계값 미만) 테스트"""
    user.login_fail_count = 0
    user.save()
    for _ in range(4):
        repo.update_login_fail_count(user, is_success=False)
    user.refresh_from_db()
    assert user.login_fail_count == 4
    assert user.account_locked_until is None


@pytest.mark.django_db
def test_update_login_fail_count_failure_with_lock(repo, user):
    """로그인 실패 시 계정 잠금 발생 테스트"""
    user.login_fail_count = 4  # 5번째 실패를 유도
    user.save()

    # 5번째 실패 시 AccountLockedException 발생 및 잠금 시간 설정
    with pytest.raises(AccountLockedException):
        repo.update_login_fail_count(user, is_success=False)

    user.refresh_from_db()
    assert user.login_fail_count == 5
    assert user.account_locked_until is not None
    # 잠금 시간이 미래인지 대략적으로 확인
    assert user.account_locked_until > django_timezone.now()


# ----------------------------------------------------------------------
# 3. Two-Factor Authentication (2FA) Tests
# ----------------------------------------------------------------------


# --- (A) 2FA 기능 활성화 환경 (settings.IS_TEST_ENV=False) ---
@pytest.mark.skipif(settings.IS_TEST_ENV, reason="Requires TOTPDevice to be imported")
@pytest.mark.django_db
def test_2fa_create_user_and_device_success(repo, password, user):
    """사용자 생성 시 2FA 장치 생성 성공 테스트"""
    email = "2fa_new@example.com"
    new_user = repo.create_user(email=email, password=password, enable_2fa=True)

    device = TOTPDevice.objects.filter(user=new_user).first()
    assert device is not None
    assert device.confirmed is False


@pytest.mark.skipif(settings.IS_TEST_ENV, reason="Requires TOTPDevice to be imported")
@pytest.mark.django_db
def test_2fa_getters_success(repo, user):
    """확정/미확정 2FA 장치 조회 성공 테스트"""
    # 1. 미확정 장치 생성
    unconfirmed_dev = TOTPDevice.objects.create(user=user, name="d1", confirmed=False)
    assert repo.get_user_unconfirmed_2fa_device(user) == unconfirmed_dev
    assert repo.get_user_confirmed_2fa_device(user) is None

    # 2. 확정 장치 생성 (미확정 삭제)
    unconfirmed_dev.delete()
    confirmed_dev = TOTPDevice.objects.create(user=user, name="d2", confirmed=True)
    assert repo.get_user_confirmed_2fa_device(user) == confirmed_dev
    assert repo.get_user_unconfirmed_2fa_device(user) is None


@pytest.mark.skipif(settings.IS_TEST_ENV, reason="Requires TOTPDevice to be imported")
@pytest.mark.django_db
def test_2fa_create_device_success(repo, user):
    """새로운 2FA 장치 생성 성공 테스트"""
    device = repo.create_2fa_device(user)
    assert isinstance(device, TOTPDevice)
    assert device.user == user
    assert device.confirmed is False


# --- (B) 2FA 기능 비활성화 환경 (NameError 분기 커버) ---
@pytest.mark.skipif(
    not settings.IS_TEST_ENV, reason="Only runs when IS_TEST_ENV is True"
)
@pytest.mark.django_db
def test_2fa_methods_handle_name_error_in_test_env(repo, user, mocker, password):
    """
    settings.IS_TEST_ENV=True일 때 TOTPDevice가 정의되지 않아 NameError가 발생하며,
    이때 모든 2FA 메서드가 None을 반환하거나 오류 없이 작동하는지 테스트합니다.
    """
    # 💡 NameError를 강제로 발생시키기 위해 TOTPDevice를 None으로 설정
    global TOTPDevice
    original_TOTPDevice = TOTPDevice
    TOTPDevice = None

    # 1. create_user: NameError 발생 시 try/except로 무시되는지 확인
    email = "2fa_fail@example.com"
    _ = repo.create_user(email=email, password=password, enable_2fa=True)
    assert User.objects.filter(email=email).exists()  # 사용자는 생성되어야 함

    # 2. get_user_confirmed_2fa_device: NameError 발생 시 None 반환
    assert repo.get_user_confirmed_2fa_device(user) is None

    # 3. get_user_unconfirmed_2fa_device: NameError 발생 시 None 반환
    assert repo.get_user_unconfirmed_2fa_device(user) is None

    # 4. create_2fa_device: NameError 발생 시 None 반환 확인
    assert repo.create_2fa_device(user) is None

    # Mocking 복원 (다른 테스트에 영향 방지)
    TOTPDevice = original_TOTPDevice
