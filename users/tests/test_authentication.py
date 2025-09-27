from unittest.mock import patch

import pytest
from rest_framework.exceptions import AuthenticationFailed

from users.authentication import JWTAuthentication
from users.exceptions import TokenAuthenticationFailed


@pytest.mark.django_db
def test_authenticate_with_valid_bearer_token(create_user, token_service_fixture):
    user, _ = create_user("user@example.com")
    jwt_auth = JWTAuthentication()

    valid_token = "valid.token.value"
    payload = {"user_id": user.id}

    with (
        patch.object(
            token_service_fixture,
            "is_valid_access_token",
            return_value=payload,
        ) as mock_token_is_valid,
        patch(
            "users.authentication.token_service",
            new=token_service_fixture,
        ),
        patch("users.authentication.user_repo") as mock_user_repo,
    ):
        mock_user_repo.get_user_by_id.return_value = user

        # Authorization 헤더에 Bearer 토큰 포함
        class DummyRequest:
            headers = {"Authorization": f"Bearer {valid_token}"}
            COOKIES = {}

        user_obj, auth = jwt_auth.authenticate(DummyRequest())
        assert user_obj == user
        assert auth is None
        mock_token_is_valid.assert_called_once_with(valid_token)
        mock_user_repo.get_user_by_id.assert_called_once_with(user.id)


@pytest.mark.django_db
def test_authenticate_with_cookie_token(create_user, token_service_fixture):
    user, _ = create_user("user@example.com")
    jwt_auth = JWTAuthentication()

    valid_token = "valid.token.value"
    payload = {"user_id": user.id}

    with (
        patch.object(
            token_service_fixture,
            "is_valid_access_token",
            return_value=payload,
        ),
        patch(
            "users.authentication.token_service",
            new=token_service_fixture,
        ),
        patch("users.authentication.user_repo") as mock_user_repo,
    ):
        mock_user_repo.get_user_by_id.return_value = user

        class DummyRequest:
            headers = {}
            COOKIES = {"access_token": valid_token}

        user_obj, auth = jwt_auth.authenticate(DummyRequest())
        assert user_obj == user
        assert auth is None


def test_authenticate_raises_authentication_failed_for_invalid_token():
    jwt_auth = JWTAuthentication()
    invalid_token = "invalid.token.value"

    class DummyRequest:
        headers = {"Authorization": f"Bearer {invalid_token}"}
        COOKIES = {}

    with patch(
        "users.authentication.token_service.is_valid_access_token",
        side_effect=TokenAuthenticationFailed("Invalid token"),
    ):
        with pytest.raises(AuthenticationFailed) as excinfo:
            jwt_auth.authenticate(DummyRequest())
        assert "Invalid token" in str(excinfo.value)


def test_authenticate_raises_authentication_failed_on_malformed_header():
    jwt_auth = JWTAuthentication()

    class DummyRequest1:
        headers = {"Authorization": "MalformedHeaderWithoutBearer"}
        COOKIES = {}

    class DummyRequest2:
        headers = {"Authorization": "Bearer"}
        COOKIES = {}

    with pytest.raises(AuthenticationFailed):
        jwt_auth.authenticate(DummyRequest1())

    with pytest.raises(AuthenticationFailed):
        jwt_auth.authenticate(DummyRequest2())


def test_authenticate_returns_none_if_no_token():
    jwt_auth = JWTAuthentication()

    class DummyRequest:
        headers = {}
        COOKIES = {}

    assert jwt_auth.authenticate(DummyRequest()) is None
