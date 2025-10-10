import secrets
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.http import urlsafe_base64_encode

from users.exceptions import (
    PasswordMismatchException,
    UserNotFoundException,
)
from users.models import User
from users.repositories.login_fail_lock_repository import LoginFailLockRepository
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService

try:
    from django_otp.plugins.otp_totp.models import TOTPDevice
except ImportError:
    TOTPDevice = None


try:
    from django_otp.plugins.otp_totp.models import TOTPDevice
except ImportError:
    TOTPDevice = None

# 모든 테스트에 transaction=True 옵션 전역 적용
pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(django_db_blocker, password):
    with django_db_blocker.unblock():
        user = User.objects.create_user(email="testing@example.com")
        user.set_password(password)
        user.save()
        user.user_profile.nickname = "test_nick"
        user.user_profile.save()
        return user


@pytest.fixture
def mock_redis_repo(mocker):
    mock = mocker.MagicMock(spec=LoginFailLockRepository)
    mock.is_account_locked.return_value = False
    mock.ACCOUNT_LOCK_DURATION_SECONDS = 600
    return mock


@pytest.fixture
def service(db, mock_redis_repo):
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    return UserService(user_repo, token_repo, token_service, mock_redis_repo)


@pytest.fixture
def mock_user_service(mocker):
    return mocker.Mock(spec=UserService)


def mock_2fa_repo(mocker, user):
    mock_device = MagicMock(
        confirmed=False,
        user=user,
        save=MagicMock(),
        verify_token=MagicMock(return_value=True),
        config_url="otp_uri_mock",
        id=1,
    )
    mock_confirmed = mocker.patch.object(
        UserRepository, "get_user_confirmed_2fa_device", return_value=None, create=True
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
    return mock_confirmed, mock_unconfirmed, mock_create, mock_delete_all, mock_device


@pytest.mark.parametrize(
    "email, expected",
    [("testing@example.com", True), ("nonexistent@example.com", False)],
)
def test_check_email_exists(service, user, email, expected):
    result = service.check_email_exists(email)
    assert result is expected


@pytest.mark.django_db
def test_change_user_password_and_blacklist(service, user, mocker):
    new_pw = secrets.token_urlsafe(12)
    mocker.patch.object(service.token_repo, "blacklist_all_user_tokens")

    service.change_user_password(user, new_pw)
    user.refresh_from_db()

    assert user.check_password(new_pw)
    service.token_repo.blacklist_all_user_tokens.assert_called_once_with(user)


@pytest.mark.django_db
def test_delete_user(service, user, password):
    with pytest.raises(
        PasswordMismatchException, match="비밀번호가 올바르지 않습니다."
    ):
        service.delete_user(user, "wrongpassword")

    result = service.delete_user(user, password)
    assert result is True
    with pytest.raises(User.DoesNotExist):
        User.objects.get(pk=user.pk)


@pytest.mark.django_db
def test_get_user_profile(service, user):
    profile = service.get_user_profile(user)
    assert profile.user == user
    assert profile.nickname == "test_nick"


@pytest.mark.django_db
def test_authenticate_user_success(service, user, password, mock_redis_repo):
    retrieved_user = service.authenticate_user(user.email, password)
    assert retrieved_user == user
    mock_redis_repo.is_account_locked.assert_called_once_with(user.id)
    mock_redis_repo.clear_login_attempts.assert_called_once_with(user.id)
    mock_redis_repo.record_login_failure.assert_not_called()


@pytest.mark.django_db
def test_authenticate_user_account_locked(service, user, password, mock_redis_repo):
    mock_redis_repo.is_account_locked.return_value = True
    with pytest.raises(ValueError, match=r"계정.*잠겼.*분.*"):
        service.authenticate_user(user.email, password)


@pytest.mark.django_db
def test_authenticate_user_inactive(service, user, password):
    user.is_active = False
    user.save()
    with pytest.raises(ValueError, match="비활성 사용자입니다."):
        service.authenticate_user(user.email, password)


@pytest.mark.django_db
def test_authenticate_user_password_mismatch_no_lock(service, user, mock_redis_repo):
    LIMIT = 5
    CURRENT = 3
    REMAINING = LIMIT - CURRENT
    mock_redis_repo.record_login_failure.return_value = {
        "current_count": CURRENT,
        "limit": LIMIT,
        "is_locked": False,
        "lock_duration_minutes": 10,
    }
    with pytest.raises(PasswordMismatchException) as excinfo:
        service.authenticate_user(user.email, "wrongpass")
    expected_msg = f"비밀번호가 올바르지 않습니다. (현재 실패 횟수: {CURRENT}/{LIMIT}회). {REMAINING}회 추가 실패 시 계정이 잠금 처리됩니다."
    assert str(excinfo.value) == expected_msg


@pytest.mark.django_db
def test_authenticate_user_password_mismatch_with_lock(service, user, mock_redis_repo):
    LIMIT = 5
    DURATION = 10
    mock_redis_repo.record_login_failure.return_value = {
        "current_count": LIMIT,
        "limit": LIMIT,
        "is_locked": True,
        "lock_duration_minutes": DURATION,
    }
    with pytest.raises(PasswordMismatchException) as excinfo:
        service.authenticate_user(user.email, "wrongpass")
    expected_msg = f"비밀번호가 올바르지 않습니다. 로그인 실패 횟수({LIMIT}회)를 초과하여 계정이 {DURATION}분 동안 잠금 처리되었습니다."
    assert str(excinfo.value) == expected_msg


@pytest.mark.django_db
def test_authenticate_user_user_not_found(service, mocker, password):
    mocker.patch.object(
        service.user_repo, "get_user_by_email", side_effect=UserNotFoundException()
    )
    with pytest.raises(UserNotFoundException):
        service.authenticate_user("noexist@example.com", password)


@pytest.mark.django_db
def test_send_password_reset_email_success_and_notfound(service, user, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    service.send_password_reset_email(user.email, "example.com")
    assert len(mail.outbox) == 1
    assert "비밀번호 재설정" in mail.outbox[0].subject

    service.user_repo.get_user_by_email = MagicMock(side_effect=UserNotFoundException)
    service.send_password_reset_email("noexist@example.com", "example.com")
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_reset_password_success(service, user):
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    new_pw = secrets.token_urlsafe(12)
    service.token_repo.blacklist_all_user_tokens = MagicMock()

    result = service.reset_password(uid, token, new_pw)
    assert result is True
    user.refresh_from_db()
    assert user.check_password(new_pw)


@pytest.mark.django_db
def test_reset_password_same_as_old(service, user, password):
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    with pytest.raises(PasswordMismatchException):
        service.reset_password(uid, token, password)


@pytest.mark.django_db
def test_reset_password_invalid_link_and_token(service, user, mocker):
    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)

    with pytest.raises(ValueError):
        service.reset_password("baduid", token, "pass")

    with pytest.raises(ValueError):
        service.reset_password(uid, "badtoken", "pass")

    mocker.patch.object(
        service.user_repo, "get_user_by_id", side_effect=UserNotFoundException
    )
    with pytest.raises(ValueError):
        service.reset_password(uid, token, "pass")

    mocker.patch("django.utils.http.urlsafe_base64_decode", side_effect=TypeError)
    with pytest.raises(ValueError):
        service.reset_password(uid, token, "pass")


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_get_2fa_setup_status(service, user, mocker):
    mock_confirmed, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)
    mock_confirmed.return_value = None
    mock_unconfirmed.return_value = None
    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending is None

    mock_unconfirmed.return_value = mock_device
    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending == mock_device


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_setup_2fa(service, user, mocker):
    mock_confirmed, mock_unconfirmed, mock_create, _, mock_device = mock_2fa_repo(
        mocker, user
    )

    mock_confirmed.return_value = None
    mock_unconfirmed.return_value = None
    device = service.setup_2fa(user)
    mock_create.assert_called_once_with(user)
    assert device == mock_device

    mock_confirmed.return_value = mock_device
    mock_unconfirmed.return_value = None
    device = service.setup_2fa(user)
    assert device == mock_device


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_setup_2fa_pending_reuse(service, user, mocker):
    mock_confirmed, mock_unconfirmed, mock_create, _, mock_device = mock_2fa_repo(
        mocker, user
    )

    mock_confirmed.return_value = None
    mock_unconfirmed.return_value = mock_device
    device = service.setup_2fa(user)
    assert device == mock_device
    mock_create.assert_not_called()


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_confirm_2fa(service, user, mocker):
    _, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)

    mock_unconfirmed.return_value = None
    result = service.confirm_2fa(user, "anycode")
    assert result is False

    mock_unconfirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    result = service.confirm_2fa(user, "wrongcode")
    assert result is False

    mock_device.verify_token.return_value = True
    result = service.confirm_2fa(user, "validcode")
    assert result is True
    mock_device.save.assert_called_once()
    assert mock_device.confirmed is True


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_verify_2fa(service, user, mocker):
    mock_confirmed, _, _, _, mock_device = mock_2fa_repo(mocker, user)

    mock_confirmed.return_value = None
    with pytest.raises(ValueError):
        service.verify_2fa(user.email, "any")

    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    with pytest.raises(ValueError):
        service.verify_2fa(user.email, "wrongcode")

    mock_device.verify_token.return_value = True
    user_auth = service.verify_2fa(user.email, "validcode")
    assert user_auth == user


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_verify_2fa_by_user(service, user, mocker):
    mock_confirmed, _, _, _, mock_device = mock_2fa_repo(mocker, user)

    mock_confirmed.return_value = None
    result = service.verify_2fa_by_user(user, "any")
    assert result is False

    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = False
    result = service.verify_2fa_by_user(user, "wrongcode")
    assert result is False

    mock_confirmed.return_value = mock_device
    mock_device.verify_token.return_value = True
    result = service.verify_2fa_by_user(user, "validcode")
    assert result is True


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_disable_2fa(service, user, mocker):
    _, _, _, mock_delete_all, _ = mock_2fa_repo(mocker, user)

    result = service.disable_2fa(user)
    assert result is True
    mock_delete_all.assert_called_once_with(user)


@pytest.mark.skipif(not TOTPDevice, reason="django_otp or TOTPDevice not available")
@pytest.mark.django_db
def test_login_with_optional_2fa_full_flow(service, user, mocker, password):
    mock_confirmed, mock_unconfirmed, _, _, mock_device = mock_2fa_repo(mocker, user)

    def mock_auth(*args, **kwargs):
        service.redis_repo.clear_login_attempts.reset_mock()
        return user

    mocker.patch.object(service, "authenticate_user", side_effect=mock_auth)

    MOCK_TEMP_ACCESS = "temp_access_token_mock"
    MOCK_TEMP_REFRESH = "temp_refresh_token_mock"
    mock_temp_tokens = (MOCK_TEMP_ACCESS, MOCK_TEMP_REFRESH, timedelta(minutes=5))
    mocker.patch.object(
        service.token_service,
        "generate_temporary_tokens",
        return_value=mock_temp_tokens,
    )

    mock_unconfirmed.return_value = None
    mock_confirmed.return_value = None
    res = service.login_with_optional_2fa(user.email, password, code=None)
    assert res == (user, True, False, "none", None, None)
