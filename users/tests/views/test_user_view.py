import uuid
from unittest.mock import MagicMock

import pytest
from django.urls import reverse

from users.exceptions import PasswordMismatchException


class FlexiMock(MagicMock):
    """
    MagicMock을 상속받아 딕셔너리처럼 .get()과 [] 접근을 지원하는 Mock 객체.
    (conftest.py에 정의되어 있지만, 임포트 문제 방지를 위해 테스트 파일에 재정의)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, spec_set=dict, **kwargs)
        # .get('key', default) 구문 지원
        self.get = lambda x, default=None: getattr(self, x, default)
        # ['key'] 구문 지원
        self.__getitem__.side_effect = lambda key: getattr(self, key)


@pytest.mark.django_db
class TestUser:
    def test_profile_get(self, authenticated_client, mocker):
        mock_profile = FlexiMock()
        mock_profile.nickname = "테스터"

        # 뷰에서 UserService를 생성하므로, UserService 내부의 get_user_profile 호출을 모킹해야 함
        mocker.patch(
            "users.services.user_service.UserService.get_user_profile",
            return_value=mock_profile,
        )

        url = reverse("user-profile")
        response = authenticated_client.get(url)
        assert response.status_code == 200

    def test_profile_get_not_found(self, authenticated_client, mocker):
        mocker.patch(
            "users.services.user_service.UserService.get_user_profile",
            return_value=None,
        )

        url = reverse("user-profile")
        response = authenticated_client.get(url)
        assert response.status_code == 404

    def test_profile_patch(self, authenticated_client, mocker):
        mock_profile = FlexiMock()
        mock_profile.nickname = "oldnick"

        mocker.patch(
            "users.services.user_service.UserService.get_user_profile",
            return_value=mock_profile,
        )
        # Serializer.save가 호출되면 모킹 객체를 반환하지 않으므로, 실제 저장 로직을 테스트하지 않음
        # 이 테스트는 Serializer.save가 성공했음을 모킹할 필요 없이 DRF 동작을 따릅니다.
        # Serializer 자체를 모킹하는 것이 더 안전함:
        mock_serializer = FlexiMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"nickname": "newnick"}
        mock_serializer.save.return_value = None # save 호출 모킹

        mocker.patch(
            "users.serializers.UserProfileSerializer.__new__",
            return_value=mock_serializer
        )

        url = reverse("user-profile")
        response = authenticated_client.patch(url, {"nickname": "newnick"})
        assert response.status_code == 200

    def test_profile_patch_not_found(self, authenticated_client, mocker):
        mocker.patch(
            "users.services.user_service.UserService.get_user_profile",
            return_value=None,
        )

        url = reverse("user-profile")
        response = authenticated_client.patch(url, {"nickname": "newnick"})
        assert response.status_code == 404

    def test_password_change(self, authenticated_client, mocker):
        user = authenticated_client.user
        pwd = authenticated_client.password

        # 뷰 코드를 UserService로 변경했으므로, UserService를 모킹하는 것이 정확합니다.
        mocker.patch(
            "users.services.user_service.UserService.change_user_password",
            return_value=True,
        )

        url = reverse("user-password-change")
        response = authenticated_client.patch(
            url,
            {
                # 이 값은 serializer.is_valid()가 통과하도록만 합니다.
                "current_password": pwd,
                "new_password": "NewPass123!",
                "new_password_confirm": "NewPass123!",
            },
        )
        assert response.status_code == 200
        # 응답 쿠키가 삭제되었는지 확인하는 assert 추가 권장

    def test_password_change_invalid(self, authenticated_client, mocker):
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
        pwd = authenticated_client.password

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
        mocker.patch(
            "users.services.user_service.UserService.delete_user",
            side_effect=PasswordMismatchException(),
        )

        url = reverse("user-delete")
        response = authenticated_client.post(url, {"password": "wrongpass"})
        assert response.status_code == 401