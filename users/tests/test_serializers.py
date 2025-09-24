import pytest

from users.serializers import UserLoginSerializer, UserRegisterSerializer
from users.tests.conftest import generate_random_password


@pytest.mark.django_db
def test_user_register_serializer_with_valid_data():
    password = generate_random_password()
    data = {
        "email": "test@valid.com",
        "password": password,
        "password_confirm": password,
        # ⚠️ Add the nickname field to the test data.
        "nickname": "testuser_nick",
    }
    serializer = UserRegisterSerializer(data=data)
    assert serializer.is_valid()
    assert "password_confirm" not in serializer.validated_data


@pytest.mark.django_db
def test_user_register_serializer_with_invalid_password_mismatch():
    password = generate_random_password()
    data = {
        "email": "test@invalid.com",
        "password": password,
        "password_confirm": "mismatched_password",
    }
    serializer = UserRegisterSerializer(data=data)
    assert not serializer.is_valid()
    assert "password_confirm" in serializer.errors


@pytest.mark.django_db
def test_user_login_serializer_with_valid_data():
    password = generate_random_password()
    data = {"email": "login@valid.com", "password": password}
    serializer = UserLoginSerializer(data=data)
    assert serializer.is_valid()
    assert serializer.validated_data["email"] == "login@valid.com"
    assert serializer.validated_data["password"] == password
