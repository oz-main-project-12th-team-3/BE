import json

from django.utils import timezone

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import ChatLog, ChatSession, Sender


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"chat_{self.session_id}"
        self.user = self.scope["user"]

        # 인증된 사용자인지, 세션이 존재하는지, 사용자가 세션의 소유주인지 확인
        if self.user.is_authenticated:
            try:
                session = await self.get_session(self.session_id)
                if session.user == self.user:
                    await self.channel_layer.group_add(
                        self.room_group_name, self.channel_name
                    )
                    await self.accept()
                else:
                    await self.close(code=403)  # 권한 없음
            except ChatSession.DoesNotExist:
                await self.close(code=404)  # 찾을 수 없음
        else:
            await self.close(code=401)  # 인증되지 않음

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # 데이터베이스에 메시지 저장
        await self.save_message(message)

        # 그룹에 메시지 방송
        await self.channel_layer.group_send(
            self.room_group_name, {"type": "chat_message", "message": message}
        )

    async def chat_message(self, event):
        message = event["message"]
        await self.send(text_data=json.dumps({"message": message}))

    @database_sync_to_async
    def get_session(self, session_id):
        return ChatSession.objects.select_related("user").get(id=session_id)

    @database_sync_to_async
    def save_message(self, message):
        session = ChatSession.objects.get(id=self.session_id)
        ChatLog.objects.create(
            session=session,
            user=self.user,
            sender=Sender.USER,
            message=message,
            timestamp=timezone.now(),
        )
