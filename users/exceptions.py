from rest_framework.exceptions import APIException


class UserNotFoundException(APIException):
    status_code = 404
    default_detail = "사용자를 찾을 수 없습니다."
    default_code = "user_not_found"


class PasswordMismatchException(APIException):
    status_code = 401
    default_detail = "비밀번호가 올바르지 않습니다."
    default_code = "password_mismatch"


class AccountLockedException(APIException):
    status_code = 403
    default_detail = "계정이 잠겼습니다."
    default_code = "account_locked"


class TokenBlacklistedException(APIException):
    status_code = 401
    default_detail = "만료되거나 무효화된 토큰입니다."
    default_code = "token_blacklisted"


class TokenAuthenticationFailed(APIException):
    status_code = 401
    default_detail = "유효하지 않거나 만료된 토큰입니다."
    default_code = "token_authentication_failed"


class TokenNotFoundException(APIException):
    status_code = 404
    default_detail = "토큰을 찾을 수 없습니다."
    default_code = "token_not_found"
