import secrets

import pytest
from rest_framework.exceptions import APIException

from users.exceptions import (
    AccountLockedException,
    EmailAlreadyExistsException,
    PasswordMismatchException,
    TfaVerificationFailedException,
    TokenAuthenticationFailed,
    TokenBlacklistedException,
    TokenNotFoundException,
    UserNotFoundException,
)

CUSTOM_EXCEPTIONS_PARAMS = [
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
    (
        TfaVerificationFailedException,
        401,
        "2차 인증 코드(OTP)가 올바르지 않습니다.",
        "tfa_verification_failed",
    ),
]


@pytest.mark.parametrize(
    "exception_class, expected_status, expected_default_detail, expected_code",
    CUSTOM_EXCEPTIONS_PARAMS,
)
def test_custom_exceptions_default_attributes(
    exception_class, expected_status, expected_default_detail, expected_code
):
    """
    모든 커스텀 예외 클래스의 status_code, default_detail, default_code 검증.
    """
    exc = exception_class()

    assert isinstance(exc, APIException)
    assert exc.status_code == expected_status
    # default_detail 확인
    assert exc.default_detail == expected_default_detail
    # detail 확인 (인자 없을 땐 default_detail과 동일)
    assert str(exc.detail) == expected_default_detail
    assert exc.default_code == expected_code


@pytest.mark.parametrize(
    "exception_class, expected_status, expected_default_detail, expected_code",
    CUSTOM_EXCEPTIONS_PARAMS,
)
def test_custom_exceptions_with_custom_message(
    exception_class, expected_status, expected_default_detail, expected_code
):
    """
    커스텀 메시지를 전달했을 때 detail 속성이 올바르게 설정되는지 검증.
    """
    custom_message = f"커스텀 테스트 메시 {secrets.token_urlsafe(8)}"

    # 예외 인스턴스 생성 시 메시지 전달
    exc = exception_class(custom_message)

    # status_code와 default_code는 기본값 유지
    assert exc.status_code == expected_status
    assert exc.default_code == expected_code

    # detail은 커스텀 메시지로 설정되어야 함
    assert str(exc.detail) == custom_message
    assert str(exc) == custom_message  # __str__도 커스텀 메시지를 반환해야 함


@pytest.mark.parametrize(
    "exception_class, expected_status, expected_default_detail, expected_code",
    CUSTOM_EXCEPTIONS_PARAMS,
)
def test_custom_exceptions_string_representation(
    exception_class, expected_status, expected_default_detail, expected_code
):
    """
    예외 인스턴스의 문자열 표현(__str__)이 detail 속성과 일치하는지 검증.
    """
    # 기본 메시지 인스턴스
    exc_default = exception_class()
    assert str(exc_default) == str(exc_default.detail)
    assert isinstance(str(exc_default), str)
    assert str(exc_default) == expected_default_detail
