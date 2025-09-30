import secrets
from datetime import timedelta

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils import timezone
from django.utils.http import urlsafe_base64_encode

from users.exceptions import PasswordMismatchException, UserNotFoundException
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


# users/tests/services/test_user_service.py (또는 해당 테스트 파일)


# users/tests/services/test_user_service.py


@pytest.fixture
def user(db, password):
    """테스트용 활성 사용자 생성 및 비밀번호 설정 (UserProfile 설정 추가)"""
    # 1. User 모델에는 email만 전달하여 생성
    # UserProfile은 post_save 시그널에 의해 자동으로 생성됨
    user = User.objects.create_user(email="testing@example.com")

    # 2. 비밀번호 설정
    user.set_password(password)
    user.save()

    # 3. UserProfile 필드 설정 (UserProfile이 자동 생성되었으므로 업데이트)
    # 💡 user_profile 관계를 사용하여 nickname을 설정합니다.
    user.user_profile.nickname = "test_nick"
    user.user_profile.enable_2fa = False  # UserRepository가 이 필드를 사용한다고 가정
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
# 1. User CRUD & Email Check
# ----------------------------------------------------------------------

# users/tests/services/test_user_service.py


@pytest.mark.django_db
def test_create_user(service):
    """사용자 생성 성공 및 이메일 중복 체크 테스트"""
    password_val = secrets.token_urlsafe(12)
    email = f"{secrets.token_urlsafe(8)}@example.com"

    # 1. 생성 성공
    user = service.create_user(email, password_val, "nick", enable_2fa=False)
    assert user.email == email
    # 💡 수정: user.user_profile.nickname으로 접근
    assert user.user_profile.nickname == "nick"

    # 2. 이메일 중복 시 ValueError 발생
    with pytest.raises(ValueError, match="이미 사용중인 이메일입니다."):
        service.create_user(email, password_val, "nick", enable_2fa=False)

    # (나머지 부분은 그대로 유지)


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
# 💡 수정: mocker 인자 추가
def test_change_user_password_and_blacklist(service, user, mocker):
    """비밀번호 변경 및 토큰 블랙리스트화 테스트 (Mocking 강화)"""
    new_pw = secrets.token_urlsafe(12)

    # 토큰 블랙리스트화 메서드 Mock
    mocker.patch.object(service.token_repo, "blacklist_all_user_tokens")

    service.change_user_password(user, new_pw)
    user.refresh_from_db()

    # 1. 비밀번호 변경 확인
    assert user.check_password(new_pw)
    # 2. 토큰 블랙리스트화 호출 확인
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
    # 1. 성공 시 반환 확인
    retrieved_user = service.authenticate_user(user.email, password)
    assert retrieved_user == user

    # 2. 로그인 성공 시 업데이트 호출 확인 (Mocking으로 대체)
    mocker.patch.object(service.user_repo, "update_login_fail_count")
    service.authenticate_user(user.email, password)
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
    # 로그인 실패 시 업데이트 호출 확인 (Mocking)
    mocker.patch.object(service.user_repo, "update_login_fail_count")

    with pytest.raises(
        PasswordMismatchException, match="비밀번호가 올바르지 않습니다."
    ):
        service.authenticate_user(user.email, "wrongpass")

    service.user_repo.update_login_fail_count.assert_called_with(user, is_success=False)


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
    # 기존 메일 외 추가 발송 없는지 확인
    service.send_password_reset_email("noexist@example.com", "example.com")
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_reset_password_success(service, user, mocker):
    """비밀번호 재설정 성공 테스트"""
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    new_pw = secrets.token_urlsafe(12)

    # 토큰 블랙리스트화 메서드 Mock
    mocker.patch.object(service.token_repo, "blacklist_all_user_tokens")

    result = service.reset_password(uid, token, new_pw)
    assert result is True

    # 1. 비밀번호 변경 확인
    user.refresh_from_db()
    assert user.check_password(new_pw)

    # 2. 토큰 블랙리스트화 호출 확인
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

    # 3. UserNotFound (uidb64는 유효하나 user_repo에서 찾지 못함)
    mocker.patch.object(
        service.user_repo,
        "get_user_by_id",
        side_effect=UserNotFoundException("not found"),
    )
    with pytest.raises(ValueError, match="유효하지 않은 비밀번호 재설정 링크입니다."):
        service.reset_password(uid, token, "pass")


# ----------------------------------------------------------------------
# 4. Two-Factor Authentication (2FA)
# ----------------------------------------------------------------------
def mock_user_repo_2fa(service, mocker, user):
    """UserRepository 인스턴스에 2FA 메서드를 Mocking하여 동적으로 추가"""

    # 💡 UserRepository 인스턴스에 Mock 메서드를 추가/재정의
    mocker.patch.object(
        service.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=None,  # 초기 Mock 값
    )
    mocker.patch.object(
        service.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=None,  # 초기 Mock 값
    )
    mocker.patch.object(
        service.user_repo,
        "create_2fa_device",
        return_value=mocker.Mock(
            confirmed=False, user=user, save=mocker.Mock(), verify_token=mocker.Mock()
        ),
    )


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
# 💡 수정: mocker 인자 추가
def test_setup_and_get_2fa_status(service, user, mocker):
    """2FA 기기 설정 및 상태 조회 테스트"""

    # 💡 UserRepository 인스턴스에 필요한 모든 2FA 메서드를 Mocking합니다.
    #    (이 Mocking이 없으면 Attribute Error가 발생합니다.)
    mock_user_repo_2fa(service, mocker, user)

    # 1. 초기 상태 확인
    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending is None

    # 2. setup_2fa: 새로운 기기 생성 (미확정)
    device = service.setup_2fa(user)
    assert device.user == user
    assert device.confirmed is False
    mock_create.assert_called_once_with(user)  # create_2fa_device 호출 확인

    # 3. 재확인: 미확정 기기 존재 상태 시뮬레이션
    mock_unconfirmed.return_value = device
    mock_confirmed.return_value = None

    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending == device


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_confirm_2fa(service, user, mocker):
    """2FA 확정 성공 및 실패 테스트"""
    device = TOTPDevice.objects.create(user=user, name="test", confirmed=False)
    mock_user_repo_2fa(service, mocker, user)

    # 1. 실패 (코드 불일치)
    mocker.patch.object(device, "verify_token", return_value=False)
    result = service.confirm_2fa(user, "wrongcode")
    assert result is False

    # 2. 성공 (코드 일치 및 confirmed=True 확인)
    mocker.patch.object(device, "verify_token", return_value=True)
    result = service.confirm_2fa(user, "validcode")
    assert result is True
    # DB에 confirmed 상태가 반영되었는지 확인 (save 호출 가정)
    device.refresh_from_db()
    assert device.confirmed is True


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_verify_2fa(service, user, mocker):
    """2FA 인증 테스트 (성공 및 실패)"""
    device = TOTPDevice.objects.create(user=user, name="test", confirmed=True)
    mock_user_repo_2fa(service, mocker, user)

    mocker.patch.object(service.user_repo, "get_user_by_email", return_value=user)
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=device
    )

    # 1. 인증 성공
    mocker.patch.object(device, "verify_token", return_value=True)
    user_authenticated = service.verify_2fa(user.email, "validcode")
    assert user_authenticated == user

    # 2. 인증 실패 (코드 불일치)
    mocker.patch.object(device, "verify_token", return_value=False)
    with pytest.raises(ValueError, match="잘못된 인증 코드입니다."):
        service.verify_2fa(user.email, "wrongcode")

    # 3. 인증 실패 (등록된 기기 없음)
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=None
    )
    with pytest.raises(ValueError, match="등록된 2FA 기기가 없습니다."):
        service.verify_2fa(user.email, "any")


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_login_with_optional_2fa_branches(service, user, mocker):
    """2FA 로그인 플로우의 분기 테스트"""
    mock_user_repo_2fa(service, mocker, user)

    mocker.patch.object(service, "authenticate_user", return_value=user)

    # 토큰 서비스 Mocking (임시 토큰 반환 확인용)
    mock_temp_tokens = ("temp_access", "temp_refresh", timedelta(minutes=5))
    mocker.patch.object(
        service.token_service,
        "generate_temporary_tokens",
        return_value=mock_temp_tokens
    )

    # Case 2: 미확정 2FA 기기 존재 -> 임시 토큰 발급
    # Mocking된 unconfirmed_device를 가져옵니다.
    unconfirmed_mock = service.user_repo.create_2fa_device(user)
    service.user_repo.get_user_unconfirmed_2fa_device.return_value = unconfirmed_mock
    service.user_repo.get_user_confirmed_2fa_device.return_value = None

    # Case 3: 미확정 2FA 기기 존재 + 유효 코드 -> 로그인 성공
    unconfirmed_mock.verify_token.return_value = True
    unconfirmed_mock.save = mocker.Mock()
    res = service.login_with_optional_2fa(user.email, "pwd", code="valid")
    assert res[1] is True  # success=True
    unconfirmed_mock.save.assert_called_once()  # 기기 확정 저장 확인

    # Case 4: 확정 2FA 기기 존재 + 유효 코드 -> 로그인 성공
    confirmed_mock = mocker.Mock(
        confirmed=True, verify_token=mocker.Mock(return_value=True)
    )
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=confirmed_mock
    )
    mocker.patch.object(
        service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None
    )

    res = service.login_with_optional_2fa(user.email, "pwd", code="valid")
    assert res[1] is True

    # Case 5: 확정 2FA 기기 존재 + 코드 불일치 -> 2FA 인증 필요
    confirmed_mock.verify_token.return_value = False
    res = service.login_with_optional_2fa(user.email, "pwd", code="invalid")
    assert res[1] is False  # success=False
    assert res[2] is False  # pending=False (2FA 인증 필요 상태)
    assert res[3] is None  # 토큰 발급 안됨
