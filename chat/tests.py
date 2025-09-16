import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from users.models import User

from .models import ChatSession


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticated_user(api_client):
    user = User.objects.create_user(
        email="testuser@example.com", password="testpassword"
    )
    api_client.force_authenticate(user=user)
    return user, api_client


@pytest.mark.django_db
class TestChatAPI:  # Changed inheritance to TestCase
    def test_unauthenticated_access(self, api_client):
        """인증되지 않은 사용자는 API에 접근할 수 없다."""
        # Use api_client for unauthenticated requests
        session_url = reverse("chat-session-list-create")
        message_url = reverse("chat-message-list-create")

        response = api_client.get(session_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = api_client.post(message_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_chat_session_create_and_list(self, authenticated_user):
        """사용자는 채팅 세션을 생성하고 자신의 세션 목록을 조회할 수 있다."""
        user, client = authenticated_user
        url = reverse("chat-session-list-create")

        # 세션 생성
        response = client.post(url, {"title": "My First Session"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "My First Session"
        assert response.data["user"] == user.id

        # 세션 목록 조회
        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["title"] == "My First Session"

    def test_chat_message_create_and_list(self, authenticated_user):
        """사용자는 자신의 세션에 메시지를 생성하고 조회할 수 있다."""
        user, client = authenticated_user
        session = ChatSession.objects.create(user=user, title="Test Session")
        url = reverse("chat-message-list-create")

        # 메시지 생성
        response = client.post(
            url, {"session": session.id, "message": "Hello, world!"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Hello, world!"
        assert response.data["sender"] == "user"

        # 메시지 목록 조회
        response = client.get(f"{url}?session_id={session.id}")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["message"] == "Hello, world!"

    def test_cannot_access_others_session(self, authenticated_user):
        """사용자는 다른 사람의 세션에 접근할 수 없다."""
        user1, client1 = authenticated_user
        user2 = User.objects.create_user(
            email="otheruser@example.com", password="otherpassword"
        )

        # user2가 세션 생성
        session_of_user2 = ChatSession.objects.create(
            user=user2, title="Other's Session"
        )

        # user1이 user2의 세션에 메시지를 보내려고 시도 -> 실패해야 함
        message_url = reverse("chat-message-list-create")
        response = client1.post(
            message_url,
            {"session": session_of_user2.id, "message": "Hi there!"},
            format="json",
        )
        # serializer.is_valid()에서 걸림
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # user1이 user2의 메시지 목록을 보려고 시도 -> 빈 목록이 나와야 함
        response = client1.get(f"{message_url}?session_id={session_of_user2.id}")
        assert (
            response.status_code == status.HTTP_403_FORBIDDEN
        )  # PermissionDenied 발생
