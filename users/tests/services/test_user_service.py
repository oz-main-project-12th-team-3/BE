import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode

from users.exceptions import (
    EmailAlreadyExistsException,
    PasswordMismatchException,
    UserNotFoundException,
)
from users.models import User
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

# 2FA 관련 클래스 (SKIP 조건이 만족하지 않을 때 사용)
try:
    from django_otp.plugins.otp_totp.models import TOTPDevice
except ImportError:
    TOTPDevice = None

# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def password():
    """랜덤 비밀번호 생성"""
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    """테스트용 활성 사용자 생성 및 비밀번호 설정"""
    # UserProfile은 post_save 시그널에 의해 자동으로 생성됨
    user = User.objects.create_user(email="testing@example.com")
    user.set_password(password)
    user.save()

    user.user_profile.nickname = "test_nick"
    user.user_profile.save()

    return user


@pytest.fixture
def service(db):
    """UserService 객체 생성"""
    # 실제 TokenRepository와 TokenService를 사용하여 Mocking 부담을 줄임
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    return UserService(user_repo, token_repo, token_service)


# ----------------------------------------------------------------------
# 2FA Helper Functions
# ----------------------------------------------------------------------


def mock_2fa_repo(mocker, user):
    """
    UserRepository 클래스에 2FA 메서드를 동적으로 주입하고 Mocking합니다.
    """
    mock_device = MagicMock(
        confirmed=False,
        user=user,
        save=MagicMock(),
        verify_token=MagicMock(return_value=True),
        config_url="otp_uri_mock",
        id=1,
    )

    # UserRepository의 2FA 관련 메서드를 모두 Mocking
    mock_confirmed = mocker.patch.object(
        UserRepository,
        "get_user_confirmed_2fa_device",
        return_value=None,
        create=True,
    )
    mock_unconfirmed = mocker.patch.object(
        UserRepository,
        "get_user_unconfirmed_2fa_device",
        return_value=None,
        create=True,
    )
    mock_create = mocker.patch.object(
        UserRepository, "create_2fa_device", return_value=mock_device, create=True
    )
    mock_delete_all = mocker.patch.object(
        UserRepository, "delete_all_2fa_devices", return_value=1, create=True
    )

    return (
        mock_confirmed,
        mock_unconfirmed,
        mock_create,
        mock_delete_all,
        mock_device,
    )


# ----------------------------------------------------------------------
# 1. User CRUD & Email Check
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_create_user(service):
    """사용자 생성 성공 및 이메일 중복 체크 테스트"""
    password_val = secrets.token_urlsafe(12)
    email = f"{secrets.token_urlsafe(8)}@example.com"

    # 1. 생성 성공
    user = service.create_user(email, password_val, "nick", enable_2fa=False)
    user.refresh_from_db()
    assert user.user_profile.nickname == "nick"

    # 2. 이메일 중복 시 EmailAlreadyExistsException 발생
    with pytest.raises(EmailAlreadyExistsException):
        service.create_user(email, password_val, "nick", enable_2fa=False)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "email, expected",
    [
        ("testing@example.com", True),
        ("nonexistent@example.com", False),
    ],
)
def test_check_email_exists(service, user, email, expected):
    """이메일 존재 여부 확인 테스트"""
    assert service.check_email_exists(email) == expected


@pytest.mark.django_db
def test_change_user_password_and_blacklist(service, user, mocker):
    """비밀번호 변경 및 토큰 블랙리스트화 테스트"""
    new_pw = secrets.token_urlsafe(12)
    mocker.patch.object(service.token_repo, "blacklist_all_user_tokens")

    service.change_user_password(user, new_pw)
    user.refresh_from_db()

    assert user.check_password(new_pw)
    service.token_repo.blacklist_all_user_tokens.assert_called_once_with(user)


@pytest.mark.django_db
def test_delete_user(service, user, password):
    """사용자 삭제 테스트 (비밀번호 불일치 및 성공)"""

    # 1. 비밀번호 불일치 시 PasswordMismatchException
    with pytest.raises(
        PasswordMismatchException, match="비밀번호가 올바르지 않습니다."
    ):
        service.delete_user(user, "wrongpassword")

    # 2. 삭제 성공
    result = service.delete_user(user, password)
    assert result is True

    with pytest.raises(User.DoesNotExist):
        User.objects.get(pk=user.pk)


@pytest.mark.django_db
def test_get_user_profile(service, user):
    """사용자 프로필 조회 테스트"""
    profile = service.get_user_profile(user)
    assert profile.user == user
    assert profile.nickname == "test_nick"


# ----------------------------------------------------------------------
# 2. Authentication
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_authenticate_user_success(service, user, password, mocker):
    """인증 성공 테스트 (실패 카운트 초기화 확인)"""
    mocker.patch.object(service.user_repo, "update_login_fail_count")

    # 1. 성공 시 반환 확인
    retrieved_user = service.authenticate_user(user.email, password)
    assert retrieved_user == user

    # 2. 로그인 성공 시 업데이트 호출 확인
    service.user_repo.update_login_fail_count.assert_called_with(user, is_success=True)


@pytest.mark.django_db
def test_authenticate_user_inactive_locked_mismatch(service, user, password, mocker):
    """비활성, 잠금, 비밀번호 불일치 테스트"""

    # 1. 비활성 사용자
    user.is_active = False
    user.save()
    with pytest.raises(ValueError, match="비활성 사용자입니다."):
        service.authenticate_user(user.email, password)
    user.is_active = True
    user.save()

    # 2. 계정 잠김
    user.account_locked_until = timezone.now() + timedelta(minutes=10)
    user.save()
    with pytest.raises(ValueError, match="계정이 잠겼습니다."):
        service.authenticate_user(user.email, password)
    user.account_locked_until = None
    user.save()

    # 3. 비밀번호 불일치
    mocker.patch.object(service.user_repo, "update_login_fail_count")
    with pytest.raises(
        PasswordMismatchException, match="비밀번호가 올바르지 않습니다."
    ):
        service.authenticate_user(user.email, "wrongpass")

    service.user_repo.update_login_fail_count.assert_called_with(user, is_success=False)


@pytest.mark.django_db
def test_authenticate_user_user_not_found(service, mocker, password):
    """인증 시 사용자 없음 테스트"""
    mocker.patch.object(
        service.user_repo,
        "get_user_by_email",
        side_effect=UserNotFoundException("not found"),
    )
    with pytest.raises(UserNotFoundException):
        service.authenticate_user("noexist@example.com", password)


# ----------------------------------------------------------------------
# 3. Password Reset
# ----------------------------------------------------------------------


@pytest.mark.django_db
def test_send_password_reset_email_success_and_notfound(
    service, user, settings, mocker
):
    """비밀번호 재설정 이메일 발송 테스트 및 사용자 없음 처리"""
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    # 1. 성공 케이스
    service.send_password_reset_email(user.email, "example.com")
    assert len(mail.outbox) == 1
    assert "비밀번호 재설정" in mail.outbox[0].subject

    # 2. 사용자 없음 시 조용히 종료되는지 확인
    mocker.patch.object(
        service.user_repo,
        "get_user_by_email",
        side_effect=UserNotFoundException("not found"),
    )
    service.send_password_reset_email("noexist@example.com", "example.com")
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_reset_password_success(service, user, mocker):
    """비밀번호 재설정 성공 테스트"""
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    new_pw = secrets.token_urlsafe(12)

    mocker.patch.object(service.token_repo, "blacklist_all_user_tokens")

    result = service.reset_password(uid, token, new_pw)
    assert result is True

    user.refresh_from_db()
    assert user.check_password(new_pw)
    service.token_repo.blacklist_all_user_tokens.assert_called_once_with(user)


@pytest.mark.django_db
def test_reset_password_invalid_link_and_token(service, user, mocker):
    """비밀번호 재설정 실패 테스트 (유효하지 않은 링크/토큰)"""
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)

    # 1. 유효하지 않은 uidb64
    with pytest.raises(ValueError, match="유효하지 않은 비밀번호 재설정 링크입니다."):
        service.reset_password("baduid", token, "pass")

    # 2. 유효하지 않은 토큰
    with pytest.raises(ValueError, match="유효하지 않은 토큰입니다."):
        service.reset_password(uid, "badtoken", "pass")

    # 3. UserNotFound (uidb64 유효, user_repo에서 못찾음)
    mocker.patch.object(
        service.user_repo,
        "get_user_by_id",
        side_effect=UserNotFoundException("not found"),
    )
    with pytest.raises(ValueError, match="유효하지 않은 비밀번호 재설정 링크입니다."):
        service.reset_password(uid, token, "pass")

    # 4. TypeError (uidb64 디코딩/force_str 오류)
    mocker.patch(
        "django.utils.http.urlsafe_base64_decode",
        side_effect=TypeError("decode error"),
    )
    with pytest.raises(ValueError, match="유효하지 않은 비밀번호 재설정 링크입니다."):
        service.reset_password(uid, token, "pass")


# ----------------------------------------------------------------------
# 4. Two-Factor Authentication (2FA) Test Logic
# ----------------------------------------------------------------------


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_get_2fa_setup_status(service, user, mocker):
    """2FA 상태 조회 테스트"""
    mock_confirmed, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)

    # 1. 초기 상태 확인
    mock_confirmed.return_value = None
    mock_unconfirmed.return_value = None
    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending is None

    # 2. 미확정 기기 존재 상태 시뮬레이션
    mock_unconfirmed.return_value = mock_device
    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending == mock_device


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_setup_2fa(service, user, mocker):
    """2FA 기기 설정 테스트 (생성 및 재사용 분기)"""
    mock_confirmed, mock_unconfirmed, mock_create, _, mock_device = mock_2fa_repo(
        mocker, user
    )

    # 1. 기기가 없을 때 -> 새로운 기기 생성
    mock_confirmed.return_value = None
    device = service.setup_2fa(user)
    mock_create.assert_called_once_with(user)
    assert device == mock_device
    mock_create.reset_mock()

    # 2. 이미 확정된 기기가 있을 때 -> 기존 기기 재사용 (생성 X)
    mock_confirmed.return_value = mock_device
    device = service.setup_2fa(user)
    assert device == mock_device
    mock_create.assert_not_called()


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_confirm_2fa(service, user, mocker):
    """2FA 확정 성공 및 실패 테스트"""
    _, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)

    # 1. 미확정 장치가 없을 때
    mock_unconfirmed.return_value = None
    result = service.confirm_2fa(user, "anycode")
    assert result is False

    # 2. 실패 (코드 불일치)
    mock_unconfirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    result = service.confirm_2fa(user, "wrongcode")
    assert result is False

    # 3. 성공 (코드 일치 및 confirmed=True 확인)
    mock_device.verify_token.return_value = True
    result = service.confirm_2fa(user, "validcode")
    assert result is True
    mock_device.save.assert_called_once()
    assert mock_device.confirmed is True


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_verify_2fa(service, user, mocker):
    """2FA 인증 테스트 (verify_2fa: email 기반)"""
    mock_confirmed, _, _, _, mock_device = mock_2fa_repo(mocker, user)

    # 1. 인증 실패 (등록된 기기 없음)
    mock_confirmed.return_value = None
    with pytest.raises(ValueError, match="등록된 2FA 기기가 없습니다."):
        service.verify_2fa(user.email, "any")

    # 2. 인증 실패 (코드 불일치)
    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    with pytest.raises(ValueError, match="잘못된 인증 코드입니다."):
        service.verify_2fa(user.email, "wrongcode")

    # 3. 인증 성공
    mock_device.verify_token.return_value = True
    user_authenticated = service.verify_2fa(user.email, "validcode")
    assert user_authenticated == user


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_verify_2fa_by_user(service, user, mocker):
    """
    verify_2fa_by_user: User 객체 기반 2FA 인증 테스트 (TfaApiView 사용)
    """
    mock_confirmed, _, _, _, mock_device = mock_2fa_repo(mocker, user)

    # 1. 인증 실패 (등록된 확정 기기 없음)
    mock_confirmed.return_value = None
    result = service.verify_2fa_by_user(user, "any")
    assert result is False

    # 2. 인증 실패 (코드 불일치)
    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    result = service.verify_2fa_by_user(user, "wrongcode")
    assert result is False

    # 3. 인증 성공
    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = True
    result = service.verify_2fa_by_user(user, "validcode")
    assert result is True


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_disable_2fa(service, user, mocker):
    """
    ⭐ disable_2fa: 2FA 비활성화 테스트
    """
    _, _, _, mock_delete_all, _ = mock_2fa_repo(mocker, user)

    result = service.disable_2fa(user)
    assert result is True
    # UserRepository의 delete_all_2fa_devices 호출 확인
    mock_delete_all.assert_called_once_with(user)


# ----------------------------------------------------------------------
# 5. 2FA Login Flow (login_with_optional_2fa) Test
# ----------------------------------------------------------------------


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_login_with_optional_2fa_full_flow(service, user, mocker, password):
    """
    login_with_optional_2fa: 2FA 상태와 코드 유무에 따른 모든 분기 테스트
    (user, login_success, tfa_required, tfa_step, temp_access, temp_refresh)
    """
    mock_confirmed, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)

    # authenticate_user 로직은 이미 위에서 테스트했으므로, 여기서는 성공 가정
    mocker.patch.object(service, "authenticate_user", return_value=user)

    MOCK_TEMP_ACCESS = "temp_access_token_mock"
    MOCK_TEMP_REFRESH = "temp_refresh_token_mock"
    mock_temp_tokens = (MOCK_TEMP_ACCESS, MOCK_TEMP_REFRESH, timedelta(minutes=5))
    mocker.patch.object(
        service.token_service,
        "generate_temporary_tokens",
        return_value=mock_temp_tokens,
    )

    # Case 1: 2FA 장치 전혀 없음 -> **로그인 성공**
    mock_unconfirmed.return_value = None
    mock_confirmed.return_value = None
    res = service.login_with_optional_2fa(user.email, password, code=None)
    assert res == (user, True, False, "none", None, None)

    # ------------------------------------------------------------------
    # Case 2: 미확정 (Pending) 기기 존재 (2FA 설정 필요, tfa_step: 'setup')
    # ------------------------------------------------------------------
    mock_unconfirmed.return_value = mock_device  # 미확정 기기 존재
    mock_confirmed.return_value = None
    mock_device.verify_token.reset_mock()
    mock_device.save.reset_mock()
    mock_device.confirmed = False  # 초기 상태 설정

    # 2-A: 코드 없음 -> 임시 토큰 발급 및 **2FA 설정 요구**
    service.token_service.generate_temporary_tokens.reset_mock()
    res = service.login_with_optional_2fa(user.email, password, code=None)
    assert res[1] is False and res[2] is True
    assert res[3] == "setup"
    assert res[4] == MOCK_TEMP_ACCESS

    # 2-B: 코드 있음 + 유효 -> **로그인 성공** 및 기기 확정
    mock_device.verify_token.return_value = True
    res = service.login_with_optional_2fa(user.email, password, code="valid")
    assert res == (user, True, False, "none", None, None)
    mock_device.save.assert_called_once()
    assert mock_device.confirmed is True

    # 2-C: 코드 있음 + 불일치 -> ValueError 예외 발생
    mock_device.verify_token.return_value = False
    with pytest.raises(ValueError, match="잘못된 2FA 인증 코드입니다."):
        service.login_with_optional_2fa(user.email, password, code="invalid")

    # ------------------------------------------------------------------
    # Case 3: 확정 (Confirmed) 기기 존재 (2FA 인증 필요, tfa_step: 'verify')
    # ------------------------------------------------------------------
    mock_confirmed.return_value = mock_device  # 확정 기기 존재
    mock_unconfirmed.return_value = None
    mock_device.confirmed = True  # 확정 상태 설정
    mock_device.verify_token.reset_mock()

    # 3-A: 코드 없음 -> 임시 토큰 발급 및 **2FA 인증 요구**
    service.token_service.generate_temporary_tokens.reset_mock()
    res = service.login_with_optional_2fa(user.email, password, code=None)
    assert res[1] is False and res[2] is True
    assert res[3] == "verify"
    assert res[4] == MOCK_TEMP_ACCESS

    # 3-B: 코드 있음 + 유효 -> **로그인 성공**
    mock_device.verify_token.return_value = True
    res = service.login_with_optional_2fa(user.email, password, code="valid")
    assert res == (user, True, False, "none", None, None)

    # 3-C: 코드 있음 + 불일치 -> ValueError 예외 발생
    mock_device.verify_token.return_value = False
    with pytest.raises(ValueError, match="잘못된 2FA 인증 코드입니다."):
        service.login_with_optional_2fa(user.email, password, code="invalid")

    # ------------------------------------------------------------------
    # Case 4: 안전 장치 (도달할 일 없음) 분기 테스트
    # ------------------------------------------------------------------
    mock_confirmed.return_value = None
    mock_unconfirmed.return_value = None
    res = service.login_with_optional_2fa(user.email, password, code="any")
    assert res == (user, True, False, "none", None, None)
