import pytest
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from users.exceptions import PasswordMismatchException
from users.repositories.token_repository import TokenRepository
from users.repositories.user_repository import UserRepository
from users.services.token_service import TokenService
from users.services.user_service import UserService


@pytest.fixture
def token_service_fixture():
    user_repo = UserRepository()
    token_repo = TokenRepository()
    return TokenService(user_repo, token_repo)


@pytest.fixture
def user_service_fixture(token_service_fixture):
    user_repo = UserRepository()
    token_repo = TokenRepository()
    return UserService(user_repo, token_repo, token_service_fixture)


@pytest.mark.django_db
def test_create_user_success(user_service_fixture):
    user = user_service_fixture.create_user(
        "test@example.com", "strongpass123", "tester", False
    )
    assert user.email == "test@example.com"


@pytest.mark.django_db
def test_authenticate_user_success(user_service_fixture, create_user):
    user, password = create_user("authuser@example.com", "mypassword")
    auth_user = user_service_fixture.authenticate_user(user.email, password)
    assert auth_user.id == user.id


@pytest.mark.django_db
def test_authenticate_user_fail_password(user_service_fixture, create_user):
    user, _ = create_user("failpass@example.com", "correctpass")
    with pytest.raises(PasswordMismatchException):
        user_service_fixture.authenticate_user(user.email, "wrongpass")


@pytest.mark.django_db
def test_send_password_reset_email(user_service_fixture, create_user):
    email = "reset@example.com"
    create_user(email)
    user_service_fixture.send_password_reset_email(email, domain="localhost")
    assert len(mail.outbox) == 1
    assert email in mail.outbox[0].to


@pytest.mark.django_db
def test_reset_password_success(user_service_fixture, create_user):
    user, _ = create_user("resetpass@example.com")
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)

    result = user_service_fixture.reset_password(uidb64, token, "newpass123")
    assert result is True


@pytest.mark.django_db
def test_reset_password_invalid_token(user_service_fixture, create_user):
    user, _ = create_user("resetpassinvalid@example.com")
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    with pytest.raises(ValueError):
        user_service_fixture.reset_password(uidb64, "invalidtoken", "newpass")


@pytest.mark.django_db
def test_delete_user_success(user_service_fixture, create_user):
    user, password = create_user("deluser@example.com")
    result = user_service_fixture.delete_user(user, password)
    assert result is True


@pytest.mark.django_db
def test_delete_user_fail_password(user_service_fixture, create_user):
    user, _ = create_user("deluserfail@example.com")
    with pytest.raises(PasswordMismatchException):
        user_service_fixture.delete_user(user, "wrongpassword")


import pytest


@pytest.mark.django_db
def test_create_user_email_exists(user_service_fixture, create_user):
    email = "duplicate@example.com"
    create_user(email)
    with pytest.raises(ValueError, match="이미 사용중인 이메일입니다."):
        user_service_fixture.create_user(email, "pass", "nick", False)


@pytest.mark.django_db
def test_authenticate_user_inactive_and_locked(user_service_fixture, create_user):
    user, password = create_user("lock@example.com")

    # 비활성 사용자 테스트
    user.is_active = False
    user.save()
    with pytest.raises(ValueError, match="비활성 사용자입니다."):
        user_service_fixture.authenticate_user(user.email, password)

    # 계정 잠금 테스트 - 메서드가 True를 반환하도록 Mocking 추천
    user.is_active = True
    user.save()
    # is_account_locked 메서드 Mock
    from unittest.mock import MagicMock

    user.is_account_locked = MagicMock(return_value=True)

    # UserRepository를 통해 가져오는 user 객체도 is_account_locked가 Mock 적용되어야 함
    def mock_get_user_by_email(email):
        return user

    user_service_fixture.user_repo.get_user_by_email = mock_get_user_by_email

    with pytest.raises(
        ValueError, match="계정이 잠겼습니다. 잠시 후 다시 시도해주세요."
    ):
        user_service_fixture.authenticate_user(user.email, password)


@pytest.mark.django_db
def test_login_with_optional_2fa_pending_and_confirmed(
    user_service_fixture, create_user, mocker
):
    user, password = create_user("2fauser@example.com")

    # 2FA 미사용 - 바로 로그인 성공
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=None,
    )
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=None,
    )
    result = user_service_fixture.login_with_optional_2fa(user.email, password)
    assert result[1] is True  # 로그인 성공

    # 2FA pending 상태 - 임시 토큰 발급
    pending_device_mock = mocker.Mock()
    pending_device_mock.verify_token.return_value = False
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=None,
    )
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=pending_device_mock,
    )

    result = user_service_fixture.login_with_optional_2fa(user.email, password)
    assert result[2] is True  # 2FA 인증 대기

    # 2FA confirmed 상태 - 코드 검증
    confirmed_device_mock = mocker.Mock()
    confirmed_device_mock.verify_token.return_value = True
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=confirmed_device_mock,
    )
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=None,
    )

    result = user_service_fixture.login_with_optional_2fa(
        user.email, password, code="123456"
    )
    assert result[1] is True  # 로그인 성공


@pytest.mark.django_db
def test_change_user_password_and_blacklist(user_service_fixture, create_user, mocker):
    user, password = create_user("changepw@example.com")
    mocker.spy(user_service_fixture.token_repo, "blacklist_all_user_tokens")
    user_service_fixture.change_user_password(user, "newpassword")
    assert user_service_fixture.token_repo.blacklist_all_user_tokens.call_count == 1


@pytest.mark.django_db
def test_confirm_2fa_success_and_fail(user_service_fixture, create_user, mocker):
    user, password = create_user("confirm2fa@example.com")
    device_mock = mocker.Mock()
    device_mock.verify_token.return_value = True
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_unconfirmed_2fa_device",
        return_value=device_mock,
    )

    assert user_service_fixture.confirm_2fa(user, "123456") is True

    device_mock.verify_token.return_value = False
    assert user_service_fixture.confirm_2fa(user, "000000") is False


@pytest.mark.django_db
def test_verify_2fa_success_and_fail(user_service_fixture, create_user, mocker):
    user, password = create_user("verify2fa@example.com")
    device_mock = mocker.Mock()
    device_mock.verify_token.return_value = True
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=device_mock,
    )
    mocker.patch.object(
        user_service_fixture.user_repo, "get_user_by_email", return_value=user
    )

    assert user_service_fixture.verify_2fa(user.email, "123456") == user

    device_mock.verify_token.return_value = False
    with pytest.raises(ValueError, match="잘못된 인증 코드입니다."):
        user_service_fixture.verify_2fa(user.email, "000000")


@pytest.mark.django_db
def test_verify_2fa_no_device(user_service_fixture, create_user, mocker):
    user, password = create_user("nodevice@example.com")
    mocker.patch.object(
        user_service_fixture.user_repo, "get_user_by_email", return_value=user
    )
    mocker.patch.object(
        user_service_fixture.user_repo,
        "get_user_confirmed_2fa_device",
        return_value=None,
    )

    with pytest.raises(ValueError, match="등록된 2FA 기기가 없습니다."):
        user_service_fixture.verify_2fa(user.email, "123456")
