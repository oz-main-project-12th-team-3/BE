
import pytest
from django.urls import reverse

from users.tests.conftest import FlexiMock
from users.exceptions import PasswordMismatchException


@pytest.mark.django_db
class TestUser:
    def test_profile_get(self, authenticated_client, mocker):
        user = authenticated_client.user

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
        # 이 테스트는 Serializer.save가 성공했음을 모킹
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

    def test_password_change(self, authenticated_client, mocker):
        user = authenticated_client.user
        pwd = authenticated_client.password

        mocker.patch(
            # authenticated_client가 이미 인증된 상태이므로 user_profile은 user.user_profile에서 접근 가능함
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=user.user_profile,
        )
        mocker.patch(
            "users.services.user_service.UserService.change_user_password",
            return_value=True,
        )

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

    def test_password_change_invalid(self, authenticated_client, mocker):
        user = authenticated_client.user

        mocker.patch(
            "users.services.user_service.UserService.change_user_password",
            side_effect=PasswordMismatchException(),
        )

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

    def test_user_delete(self, authenticated_client, mocker):
        user = authenticated_client.user
        pwd = authenticated_client.password

        mocker.patch(
            "users.repositories.user_repository.UserRepository.get_user_profile",
            return_value=user.user_profile,
        )
        mocker.patch(
            "users.services.user_service.UserService.delete_user",
            return_value=True,
        )

        url = reverse("user-delete")
        response = authenticated_client.post(url, {"password": pwd})
        assert response.status_code == 200

    def test_user_delete_missing_password(self, authenticated_client):
        url = reverse("user-delete")
        response = authenticated_client.post(url, {})
        assert response.status_code == 400

    def test_user_delete_invalid_password(self, authenticated_client, mocker):
        user = authenticated_client.user

        mocker.patch(
            "users.services.user_service.UserService.delete_user",
            side_effect=PasswordMismatchException(),
        )

        url = reverse("user-delete")
        response = authenticated_client.post(url, {"password": "wrongpass"})
        assert response.status_code == 401
