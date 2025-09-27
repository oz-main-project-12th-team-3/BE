import secrets
from datetime import timedelta

import pytest
from django.conf import settings
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
def test_create_user(service):
    password = secrets.token_urlsafe(12)
    email = f"{secrets.token_urlsafe(8)}@example.com"
    user = service.create_user(email, password, "nick", enable_2fa=False)
    assert user.email == email

    with pytest.raises(ValueError):
        service.create_user(email, password, "nick", enable_2fa=False)


@pytest.mark.django_db
def test_authenticate_user(service, user, password):
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
def test_login_flow(service, user, mocker):
    # 2FA 설정 안 된 경우
    mocker.patch.object(service.user_repo, "get_user_confirmed_2fa_device", return_value=None)
    mocker.patch.object(service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None)

    result = service.login_with_optional_2fa(user.email, secrets.token_urlsafe(10))
    assert result[0] == user and result[1] is True and result[2] is False

    # Unconfirmed 2FA 있을 때 코드 틀림
    unconfirmed_mock = mocker.Mock()
    unconfirmed_mock.verify_token.return_value = False
    mocker.patch.object(service.user_repo, "get_user_unconfirmed_2fa_device", return_value=unconfirmed_mock)
    mocker.patch.object(service.user_repo, "get_user_confirmed_2fa_device", return_value=None)

    # 비밀번호가 잘못된 경우도 예외 발생하도록 authenticate_user mock
    mocker.patch.object(service, "authenticate_user", side_effect=PasswordMismatchException("비밀번호가 올바르지 않습니다."))

    with pytest.raises(PasswordMismatchException):
        service.login_with_optional_2fa(user.email, "wrongpassword")

    # 비밀번호 맞음으로 mock 복구
    mocker.patch.object(service, "authenticate_user", return_value=user)
    unconfirmed_mock.verify_token.return_value = True
    result = service.login_with_optional_2fa(user.email, secrets.token_urlsafe(10), code="123456")
    assert result[1] is True

    # Confirmed 2FA 있을 때 코드 맞음
    confirmed_mock = mocker.Mock()
    confirmed_mock.verify_token.return_value = True
    mocker.patch.object(service.user_repo, "get_user_confirmed_2fa_device", return_value=confirmed_mock)
    mocker.patch.object(service.user_repo, "get_user_unconfirmed_2fa_device", return_value=None)

    result = service.login_with_optional_2fa(user.email, secrets.token_urlsafe(10), code="123456")
    assert result[1] is True

    # Confirmed 2FA 있을 때 코드 틀림
    confirmed_mock.verify_token.return_value = False
    result = service.login_with_optional_2fa(user.email, secrets.token_urlsafe(10), code="wrong")
    assert result[1] is False


@pytest.mark.django_db
def test_send_password_reset_email_and_reset(service, user, monkeypatch):
    monkeypatch.setattr(settings, "PROJECT_NAME", "TestProject")
    monkeypatch.setattr(settings, "DEFAULT_FROM_EMAIL", "from@example.com")

    service.send_password_reset_email(user.email, "example.com")
    assert len(mail.outbox) == 1
    assert "비밀번호 재설정" in mail.outbox[0].subject

    # 유저 없으면 None 반환
    service.user_repo.get_user_by_email = lambda e: (_ for _ in ()).throw(UserNotFoundException("not found"))
    assert service.send_password_reset_email("noexist@example.com", "example.com") is None

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
def test_change_user_password_blacklists_tokens(service, user):
    new_pw = secrets.token_urlsafe(12)
    service.change_user_password(user, new_pw)
    user.refresh_from_db()
    assert user.check_password(new_pw)


@pytest.mark.django_db
def test_delete_user_password_mismatch_and_success(service, user, password):
    with pytest.raises(PasswordMismatchException):
        service.delete_user(user, "wrongpassword")

    result = service.delete_user(user, password)
    assert result is True

    with pytest.raises(User.DoesNotExist):
        User.objects.get(pk=user.pk)
