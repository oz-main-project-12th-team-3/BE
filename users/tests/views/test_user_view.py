import uuid
import pytest
from unittest.mock import MagicMock
from django.urls import reverse
from users.exceptions import PasswordMismatchException


class FlexiMock(MagicMock):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        def safe_getitem(instance, key):
            # 문자열 key만 허용, 안전하게 getattr 호출
            if not isinstance(key, str):
                raise KeyError(f"Unusable key type: {type(key)} expected str")
            return getattr(instance, key)

        self.__getitem__ = safe_getitem


@pytest.mark.django_db
class TestUser:

    def test_profile_get(self, authenticated_client, mocker):
        mock_profile = FlexiMock()
        mock_profile.nickname = "테스터"

        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=mock_profile,
        )

        url = reverse("user-profile")
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_profile_get_not_found(self, authenticated_client, mocker):
        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=None,
        )

        url = reverse("user-profile")
        response = authenticated_client.get(url)
        assert response.status_code == 404

    def test_profile_patch(self, authenticated_client, mocker):
        mock_profile = FlexiMock()
        mock_profile.nickname = "oldnick"

        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=mock_profile,
        )
        mocker.patch("users.serializers.UserProfileSerializer.save", return_value=None)

        url = reverse("user-profile")
        response = authenticated_client.patch(url, {"nickname": "newnick"})
        assert response.status_code == 200

    def test_profile_patch_not_found(self, authenticated_client, mocker):
        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=None,
        )

        url = reverse("user-profile")
        response = authenticated_client.patch(url, {"nickname": "newnick"})
        assert response.status_code == 404

    def test_password_change(self, authenticated_client, create_user, mocker):
        user, pwd = create_user(f"user_{uuid.uuid4().hex}@example.com")

        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=user.user_profile,
        )
        mocker.patch(
            "users.services.user_service.UserService.change_user_password",
            return_value=True,
        )

        authenticated_client.force_authenticate(user)
        url = reverse("user-password-change")
        response = authenticated_client.patch(
            url,
            {
                "current_password": pwd,
                "new_password": "NewPass123!",
                "new_password_confirm": "NewPass123!",
            },
        )
        assert response.status_code == 200

    def test_password_change_invalid(self, authenticated_client, create_user, mocker):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")

        mocker.patch(
            "users.services.user_service.UserService.change_user_password",
            side_effect=PasswordMismatchException(),
        )

        authenticated_client.force_authenticate(user)
        url = reverse("user-password-change")
        response = authenticated_client.patch(
            url,
            {
                "current_password": "wrongpass",
                "new_password": "NewPass123!",
                "new_password_confirm": "NewPass123!",
            },
        )
        assert response.status_code == 401

    def test_user_delete(self, authenticated_client, create_user, mocker):
        user, pwd = create_user(f"user_{uuid.uuid4().hex}@example.com")

        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=user.user_profile,
        )
        mocker.patch(
            "users.services.user_service.UserService.delete_user",
            return_value=True,
        )

        authenticated_client.force_authenticate(user)
        url = reverse("user-delete")
        response = authenticated_client.post(url, {"password": pwd})
        assert response.status_code == 200

    def test_user_delete_missing_password(self, authenticated_client):
        url = reverse("user-delete")
        response = authenticated_client.post(url, {})
        assert response.status_code == 400

    def test_user_delete_invalid_password(self, authenticated_client, create_user, mocker):
        user, _ = create_user(f"user_{uuid.uuid4().hex}@example.com")

        mocker.patch(
            "users.services.user_service.UserService.delete_user",
            side_effect=PasswordMismatchException(),
        )

        authenticated_client.force_authenticate(user)
        url = reverse("user-delete")
        response = authenticated_client.post(url, {"password": "wrongpass"})
        assert response.status_code == 401
