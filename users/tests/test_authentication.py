import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import RequestFactory

from users.authentication import JWTAuthentication


@pytest.fixture
def auth_request_factory():
    """JWTAuthentication 테스트를 위한 RequestFactory 픽스처를 제공합니다."""
    return RequestFactory()


@pytest.mark.django_db
def test_authenticate_no_token_in_request(auth_request_factory):
    """요청에 토큰이 없을 때 None을 반환하는지 테스트합니다."""
    auth = JWTAuthentication()
    request = auth_request_factory.get("/")
    assert auth.authenticate(request) is None


@pytest.mark.django_db
def test_authenticate_invalid_auth_header(auth_request_factory):
    """Authorization 헤더 형식이 유효하지 않을 때 예외를 발생시키는지 테스트합니다."""
    auth = JWTAuthentication()
    request = auth_request_factory.get("/", HTTP_AUTHORIZATION="Token invalid-format")
    with pytest.raises(AuthenticationFailed, match="Bearer 토큰이어야 합니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_authenticate_invalid_token(auth_request_factory):
    """유효하지 않은 JWT 토큰에 대해 예외를 발생시키는지 테스트합니다."""
    auth = JWTAuthentication()
    request = auth_request_factory.get(
        "/", HTTP_AUTHORIZATION="Bearer invalid.token.string"
    )
    with pytest.raises(AuthenticationFailed, match="유효하지 않은 토큰입니다."):
        auth.authenticate(request)


@pytest.mark.django_db
def test_authenticate_token_from_header_success(auth_request_factory, user_with_tokens):
    """Authorization 헤더의 유효한 토큰으로 인증이 성공하는지 테스트합니다."""
    user, access_token, _, _ = user_with_tokens
    auth = JWTAuthentication()
    request = auth_request_factory.get("/", HTTP_AUTHORIZATION=f"Bearer {access_token}")
    authenticated_user, _ = auth.authenticate(request)
    assert authenticated_user == user


@pytest.mark.django_db
def test_authenticate_token_from_cookies_success(
    auth_request_factory, user_with_tokens
):
    """쿠키의 유효한 토큰으로 인증이 성공하는지 테스트합니다."""
    user, access_token, _, _ = user_with_tokens
    auth = JWTAuthentication()
    request = auth_request_factory.get("/")
    request.COOKIES = {"access_token": access_token}
    authenticated_user, _ = auth.authenticate(request)
    assert authenticated_user == user


@pytest.mark.django_db
def test_authenticate_with_expired_token(auth_request_factory, user_with_profile):
    """만료된 토큰으로 인증을 시도할 때 예외를 발생시키는지 테스트합니다."""
    from datetime import timedelta

    import jwt
    from django.utils import timezone

    # 만료된 토큰 생성
    user, _ = user_with_profile
    payload = {
        "user_id": user.id,
        "exp": timezone.now() - timedelta(seconds=1),
        "iat": timezone.now() - timedelta(minutes=1),
    }
    expired_token = jwt.encode(payload, "test-secret", algorithm="HS256")

    auth = JWTAuthentication()
    request = auth_request_factory.get(
        "/", HTTP_AUTHORIZATION=f"Bearer {expired_token}"
    )
    with pytest.raises(AuthenticationFailed, match="토큰이 만료되었습니다."):
        auth.authenticate(request)
