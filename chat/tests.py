import asyncio

import pytest
from channels.testing import WebsocketCommunicator
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from config.asgi import application
from users.models import User

from .models import ChatLog, ChatSession, Sender


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
class TestChatAPI:
    def test_unauthenticated_access(self, api_client):
        """인증되지 않은 사용자는 API에 접근할 수 없다."""
        session_url = reverse("chat-sessions-list-create")
        message_url = reverse("chat-messages-list-create")

        response = api_client.get(session_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = api_client.post(message_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_chat_session_create_and_list(self, authenticated_user):
        """사용자는 채팅 세션을 생성하고 자신의 세션 목록을 조회할 수 있다."""
        user, client = authenticated_user
        url = reverse("chat-sessions-list-create")

        response = client.post(url, {"title": "My First Session"}, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["title"] == "My First Session"
        assert response.data["user"] == user.id

        response = client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["title"] == "My First Session"

    def test_chat_message_create_and_list(self, authenticated_user):
        """사용자는 자신의 세션에 메시지를 생성하고 조회할 수 있다."""
        user, client = authenticated_user
        session = ChatSession.objects.create(user=user, title="Test Session")
        url = reverse("chat-messages-list-create")

        response = client.post(
            url, {"session": session.id, "message": "Hello, world!"}, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["message"] == "Hello, world!"
        assert response.data["sender"] == "user"

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

        session_of_user2 = ChatSession.objects.create(
            user=user2, title="Other's Session"
        )

        message_url = reverse("chat-messages-list-create")
        response = client1.post(
            message_url,
            {"session": session_of_user2.id, "message": "Hi there!"},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        response = client1.get(f"{message_url}?session_id={session_of_user2.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
class TestChatConsumer:
    def test_authenticated_user_can_connect(self):
        asyncio.run(self._test_authenticated_user_can_connect())

    async def _test_authenticated_user_can_connect(self):
        user = await User.objects.acreate(email="test@example.com", password="password")
        session = await ChatSession.objects.acreate(user=user, title="Test Session")

        communicator = WebsocketCommunicator(
            application, f"/ws/chat-sessions/{session.id}/"
        )
        communicator.scope["user"] = user

        connected, _ = await communicator.connect()
        assert connected
        await communicator.disconnect()

    def test_unauthenticated_user_cannot_connect(self):
        asyncio.run(self._test_unauthenticated_user_cannot_connect())

    async def _test_unauthenticated_user_cannot_connect(self):
        from django.contrib.auth.models import AnonymousUser

        user = await User.objects.acreate(email="test@example.com", password="password")
        session = await ChatSession.objects.acreate(user=user, title="Test Session")

        communicator = WebsocketCommunicator(
            application, f"/ws/chat-sessions/{session.id}/"
        )
        communicator.scope["user"] = AnonymousUser()

        connected, close_code = await communicator.connect()
        assert not connected
        assert close_code == 401

    def test_user_cannot_connect_to_others_session(self):
        asyncio.run(self._test_user_cannot_connect_to_others_session())

    async def _test_user_cannot_connect_to_others_session(self):
        user1 = await User.objects.acreate(
            email="user1@example.com", password="password"
        )
        user2 = await User.objects.acreate(
            email="user2@example.com", password="password"
        )
        session_of_user2 = await ChatSession.objects.acreate(
            user=user2, title="User2 Session"
        )

        communicator = WebsocketCommunicator(
            application, f"/ws/chat-sessions/{session_of_user2.id}/"
        )
        communicator.scope["user"] = user1

        connected, close_code = await communicator.connect()
        assert not connected
        assert close_code == 403

    def test_receive_and_save_message(self):
        asyncio.run(self._test_receive_and_save_message())

    async def _test_receive_and_save_message(self):
        user = await User.objects.acreate(email="test@example.com", password="password")
        session = await ChatSession.objects.acreate(user=user, title="Test Session")

        communicator = WebsocketCommunicator(
            application, f"/ws/chat-sessions/{session.id}/"
        )
        communicator.scope["user"] = user
        await communicator.connect()

        await communicator.send_json_to({"message": "hello"})

        response = await communicator.receive_json_from()
        assert response["message"] == "hello"

        log_exists = await ChatLog.objects.filter(
            session=session, user=user, message="hello", sender=Sender.USER
        ).aexists()
        assert log_exists

        await communicator.disconnect()
