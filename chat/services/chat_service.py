from django.db.models import F, OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from users.models import User

from ..models import ChatLog, ChatSession, Sender, VoiceLog


def create_chat_message(user: User, session_id: int, message: str) -> ChatLog:
    """
    Creates a new chat message in a session after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise PermissionDenied("Chat session not found.")

    if session.user != user:
        raise PermissionDenied(
            "You do not have permission to post to this chat session."
        )

    chat_log = ChatLog.objects.create(
        user=user,
        session=session,
        message=message,
        sender=Sender.USER,
        timestamp=timezone.now(),
    )
    return chat_log


def get_chat_messages_for_session(user: User, session_id: int):
    """
    Retrieves all chat messages for a given session, after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        return ChatLog.objects.none()

    if session.user != user:
        raise PermissionDenied("You do not have permission to view this chat session.")

    return ChatLog.objects.filter(session_id=session_id).order_by("timestamp")


def get_chat_sessions_for_user(user: User):
    """
    Retrieves all chat sessions for a given user, annotated with the last message
    and its timestamp for ordering.
    """
    last_message_subquery = ChatLog.objects.filter(session=OuterRef("pk")).order_by(
        "-timestamp"
    )

    sessions = (
        ChatSession.objects.filter(user=user)
        .annotate(
            last_message=Subquery(last_message_subquery.values("message")[:1]),
            last_message_timestamp=Subquery(
                last_message_subquery.values("timestamp")[:1]
            ),
        )
        .order_by(F("last_message_timestamp").desc(nulls_last=True))
    )

    return sessions


def create_voice_log(user: User, session_id: int, input_audio_url: str) -> VoiceLog:
    """
    Creates a new voice log for a session after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise PermissionDenied("Chat session not found.")

    if session.user != user:
        raise PermissionDenied(
            "You do not have permission to post to this chat session."
        )

    voice_log = VoiceLog.objects.create(
        user=user,
        session=session,
        input_audio_url=input_audio_url,
        timestamp=timezone.now(),
    )
    # Note: Asynchronous AI processing (STT/TTS) can be triggered from here.
    return voice_log


def get_voice_logs_for_session(user: User, session_id: int):
    """
    Retrieves all voice logs for a given session, after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        return VoiceLog.objects.none()

    if session.user != user:
        raise PermissionDenied("You do not have permission to view this chat session.")

    return VoiceLog.objects.filter(session_id=session_id).order_by("timestamp")
