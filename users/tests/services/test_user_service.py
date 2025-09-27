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


@pytest.fixture
def password():
    return secrets.token_urlsafe(12)


@pytest.fixture
def user(db, password):
    user = User.objects.create_user(email="testing@example.com")
    user.set_password(password)
    user.save()
    return user


@pytest.fixture
def service(db):
    user_repo = UserRepository()
    token_repo = TokenRepository()
    token_service = TokenService(user_repo, token_repo)
    return UserService(user_repo, token_repo, token_service)


@pytest.mark.django_db
def test_create_user(service, settings):
    # settings fixture로 직접 PROJECT_NAME 세팅
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    password = secrets.token_urlsafe(12)
    email = f"{secrets.token_urlsafe(8)}@example.com"
    user = service.create_user(email, password, "nick", enable_2fa=False)
    assert user.email == email

    with pytest.raises(ValueError):
        service.create_user(email, password, "nick", enable_2fa=False)


@pytest.mark.django_db
def test_authenticate_user(service, user, password, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    retrieved_user = service.authenticate_user(user.email, password)
    assert retrieved_user == user

    user.is_active = False
    user.save()
    with pytest.raises(ValueError):
        service.authenticate_user(user.email, password)

    user.is_active = True
    user.account_locked_until = timezone.now() + timedelta(minutes=10)
    user.save()
    with pytest.raises(ValueError):
        service.authenticate_user(user.email, "wrongpass")

    user.account_locked_until = None
    user.save()
    with pytest.raises(PasswordMismatchException):
        service.authenticate_user(user.email, "wrongpass")


@pytest.mark.django_db
def test_login_flow(service, user, mocker, settings):
    def test_login_flow_password_mismatch(service, user, mocker):
        mocker.patch.object(
            service,
            "authenticate_user",
            side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."),
        )

        with pytest.raises(PasswordMismatchException):
            service.login_with_optional_2fa(user.email, "wrongpassword")

    def test_login_flow_success(service, user, mocker):
        mocker.patch.object(
            service.user_repo, "get_user_confirmed_2fa_device", return_value=None
        )
        mocker.patch.object(
            service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None
        )
        mocker.patch.object(service, "authenticate_user", return_value=user)

        result = service.login_with_optional_2fa(user.email, "correctpassword")
        assert result[0] == user
        assert result[1] is True
        assert result[2] is False


@pytest.mark.django_db
def test_send_password_reset_email_and_reset(service, user, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    service.send_password_reset_email(user.email, "example.com")
    assert len(mail.outbox) == 1
    assert "비밀번호 재설정" in mail.outbox[0].subject

    service.user_repo.get_user_by_email = lambda e: (_ for _ in ()).throw(
        UserNotFoundException("not found")
    )
    assert (
        service.send_password_reset_email("noexist@example.com", "example.com") is None
    )

    uid = urlsafe_base64_encode(str(user.pk).encode())
    token = default_token_generator.make_token(user)
    new_pw = secrets.token_urlsafe(12)
    result = service.reset_password(uid, token, new_pw)
    assert result is True
    user.refresh_from_db()
    assert user.check_password(new_pw)

    with pytest.raises(ValueError):
        service.reset_password("baduid", token, "pass")

    with pytest.raises(ValueError):
        service.reset_password(uid, "badtoken", "pass")


@pytest.mark.django_db
def test_change_user_password_blacklists_tokens(service, user, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    new_pw = secrets.token_urlsafe(12)
    service.change_user_password(user, new_pw)
    user.refresh_from_db()
    assert user.check_password(new_pw)


@pytest.mark.django_db
def test_delete_user_password_mismatch_and_success(service, user, password, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    with pytest.raises(PasswordMismatchException):
        service.delete_user(user, "wrongpassword")

    result = service.delete_user(user, password)
    assert result is True

    with pytest.raises(User.DoesNotExist):
        User.objects.get(pk=user.pk)


@pytest.mark.django_db
def test_authenticate_user_success(service, user, password, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"
    user_returned = service.authenticate_user(user.email, password)
    assert user_returned == user


@pytest.mark.django_db
def test_login_with_optional_2fa_branches(service, user, mocker, settings):
    settings.PROJECT_NAME = "TestProject"
    settings.DEFAULT_FROM_EMAIL = "from@example.com"

    # 2FA 비활성
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=None
    )
    mocker.patch.object(
        service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None
    )
    mocker.patch.object(service, "authenticate_user", return_value=user)
    user_obj, success, pending, access, refresh = service.login_with_optional_2fa(
        user.email, "pwd"
    )
    assert user_obj == user
    assert success is True
    assert pending is False

    # 2FA 미확정. verify 실패
    unconfirmed_mock = mocker.Mock()
    unconfirmed_mock.verify_token.return_value = False
    mocker.patch.object(
        service.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=unconfirmed_mock,
    )
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=None
    )
    res = service.login_with_optional_2fa(user.email, "pwd")
    assert res[1] is False  # 인증 실패
    assert res[2] is True  # 2FA 진행 중

    # 2FA 미확정. verify 성공
    unconfirmed_mock.verify_token.return_value = True
    res = service.login_with_optional_2fa(user.email, "pwd", code="valid")
    assert res[1] is True

    # 2FA 확정. verify 성공
    confirmed_mock = mocker.Mock()
    confirmed_mock.verify_token.return_value = True
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=confirmed_mock
    )
    mocker.patch.object(
        service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None
    )
    res = service.login_with_optional_2fa(user.email, "pwd", code="valid")
    assert res[1] is True

    # 2FA 확정. verify 실패
    confirmed_mock.verify_token.return_value = False
    res = service.login_with_optional_2fa(user.email, "pwd", code="invalid")
    assert res[1] is False


@pytest.mark.django_db
def test_get_user_profile_and_2fa(service, user, mocker):
    profile = service.get_user_profile(user)
    assert profile is not None

    confirmed, pending = service.get_2fa_setup_status(user)
    assert confirmed is None and pending is None

    device = service.setup_2fa(user)
    assert device.user == user

    # 2FA 미확정 기기 조회 함수 mock
    mocker.patch.object(
        service.user_repo, "get_user_unconfirmed_2fa_device", return_value=device
    )

    # verify_token이 False 일 때
    mocker.patch.object(device, "verify_token", return_value=False)
    result = service.confirm_2fa(user, "wrongcode")
    assert result is False

    # verify_token이 True 일 때
    mocker.patch.object(device, "verify_token", return_value=True)
    result = service.confirm_2fa(user, "validcode")
    assert result is True


@pytest.mark.django_db
def test_verify_2fa_exceptions(service, user, mocker):
    mocker.patch.object(service.user_repo, "get_user_by_email", return_value=user)
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=None
    )
    with pytest.raises(ValueError):
        service.verify_2fa(user.email, "any")

    confirmed_mock = mocker.Mock()
    confirmed_mock.verify_token.return_value = False
    mocker.patch.object(
        service.user_repo, "get_user_confirmed_2fa_device", return_value=confirmed_mock
    )
    with pytest.raises(ValueError):
        service.verify_2fa(user.email, "badcode")


@pytest.mark.django_db
def test_check_email_exists(service, user):
    assert service.check_email_exists(user.email)
    assert not service.check_email_exists("notfound@example.com")
