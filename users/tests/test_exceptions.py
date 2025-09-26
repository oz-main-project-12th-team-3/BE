from users.exceptions import (
    AccountLockedException,
    PasswordMismatchException,
    TokenAuthenticationFailed,
    TokenBlacklistedException,
    TokenNotFoundException,
    UserNotFoundException,
)


def test_user_not_found_exception():
    exc = UserNotFoundException()
    assert exc.status_code == 404
    assert isinstance(exc.detail, str)


def test_password_mismatch_exception():
    exc = PasswordMismatchException()
    assert exc.status_code == 401
    assert isinstance(exc.detail, str)


def test_account_locked_exception():
    exc = AccountLockedException()
    assert exc.status_code == 403
    assert isinstance(exc.detail, str)


def test_token_blacklisted_exception():
    exc = TokenBlacklistedException()
    assert exc.status_code == 401
    assert isinstance(exc.detail, str)


def test_token_authentication_failed():
    exc = TokenAuthenticationFailed()
    assert exc.status_code == 401
    assert isinstance(exc.detail, str)


def test_token_not_found_exception():
    exc = TokenNotFoundException()
    assert exc.status_code == 404
    assert isinstance(exc.detail, str)
