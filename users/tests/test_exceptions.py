import secrets

import pytest
from rest_framework.exceptions import APIException

from users.exceptions import (
    AccountLockedException,
    EmailAlreadyExistsException,
    PasswordMismatchException,
    TokenAuthenticationFailed,
    TokenBlacklistedException,
    TokenNotFoundException,
    UserNotFoundException,
)


@pytest.mark.parametrize(
    "exception_class, expected_status, expected_detail, expected_code",
    [
        (UserNotFoundException, 404, "사용자를 찾을 수 없습니다.", "user_not_found"),
        (
            PasswordMismatchException,
            401,
            "비밀번호가 올바르지 않습니다.",
            "password_mismatch",
        ),
        (AccountLockedException, 403, "계정이 잠겼습니다.", "account_locked"),
        (
            TokenBlacklistedException,
            401,
            "만료되거나 무효화된 토큰입니다.",
            "token_blacklisted",
        ),
        (
            TokenAuthenticationFailed,
            401,
            "유효하지 않거나 만료된 토큰입니다.",
            "token_authentication_failed",
        ),
        (TokenNotFoundException, 404, "토큰을 찾을 수 없습니다.", "token_not_found"),
        (
            EmailAlreadyExistsException,
            409,
            "이미 사용 중인 이메일 주소입니다.",
            "email_already_exists",
        ),
    ],
)
def test_custom_exceptions_attributes(
    exception_class, expected_status, expected_detail, expected_code
):
    _ = secrets.token_urlsafe(16)

    exc = exception_class()

    assert isinstance(exc, APIException)
    assert exc.status_code == expected_status
    assert str(exc.detail) == expected_detail
    assert exc.default_code == expected_code


@pytest.mark.parametrize(
    "exception_class",
    [
        UserNotFoundException,
        PasswordMismatchException,
        AccountLockedException,
        TokenBlacklistedException,
        TokenAuthenticationFailed,
        TokenNotFoundException,
        EmailAlreadyExistsException,
    ],
)
def test_custom_exceptions_string_representation(exception_class):
    # 인스턴스화 후 __str__ 로 detail 반환 확인
    _ = secrets.token_urlsafe(8)
    exc = exception_class()
    assert str(exc) == str(exc.detail)
    assert isinstance(str(exc), str)
