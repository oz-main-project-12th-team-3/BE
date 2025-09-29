import json

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone

from ai.services.ai_service import ai_service
from .models import ChatLog, ChatSession, Sender


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"chat_{self.session_id}"
        self.user = self.scope["user"]

        if self.user.is_authenticated:
            try:
                session = await self.get_session(self.session_id)
                if session.user == self.user:
                    await self.channel_layer.group_add(
                        self.room_group_name, self.channel_name
                    )
                    await self.accept()
                else:
                    await self.close(code=403)
            except ChatSession.DoesNotExist:
                await self.close(code=404)
        else:
            await self.close(code=401)

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        # 1. Save user's message
        await self.save_message(message, Sender.USER)

        # 2. Get AI response
        ai_response_message = await sync_to_async(ai_service.get_gemini_response)(message)

        # 3. Save AI's message
        await self.save_message(ai_response_message, Sender.AI)

        # 4. Broadcast AI's message to the group
        await self.channel_layer.group_send(
            self.room_group_name, {
                "type": "chat_message",
                "message": ai_response_message,
                "sender": Sender.AI.value
            }
        )

    async def chat_message(self, event):
        message = event["message"]
        sender = event["sender"]
        await self.send(text_data=json.dumps({"message": message, "sender": sender}))

    @database_sync_to_async
    def get_session(self, session_id):
        return ChatSession.objects.select_related("user").get(id=session_id)

    @database_sync_to_async
    def save_message(self, message, sender):
        session = ChatSession.objects.get(id=self.session_id)
        ChatLog.objects.create(
            session=session,
            user=self.user,
            sender=sender,
            message=message,
            timestamp=timezone.now(),
        )
