from celery import shared_task
from django.contrib.auth import get_user_model
from services.ai_service import AIService

from .ai_client import client

User = get_user_model()


@shared_task
def async_ask_schedule_assistant(user_id, user_message):
    user = User.objects.get(id=user_id)
    service = AIService(client)
    reply = service.ask_schedule_assistant(user, user_message)
    return reply
