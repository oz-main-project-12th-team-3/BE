from django.db.models import F, OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from users.models import User

from ..models import ChatLog, ChatSession, Sender, VoiceLog


def create_chat_session(user: User, title: str) -> ChatSession:
    """
    Creates a new chat session for a user.
    """
    session = ChatSession.objects.create(user=user, title=title)
    return session


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


def update_chat_session(user: User, session_id: int, data: dict) -> ChatSession:
    """
    Updates a chat session's details after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise NotFound("Chat session not found.")

    if session.user != user:
        raise PermissionDenied("You do not have permission to edit this chat session.")

    for attr, value in data.items():
        setattr(session, attr, value)
    session.save()
    return session


def delete_chat_session(user: User, session_id: int):
    """
    Deletes a chat session after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise NotFound("Chat session not found.")

    if session.user != user:
        raise PermissionDenied(
            "You do not have permission to delete this chat session."
        )

    session.delete()


def create_chat_message(user: User, session_id: int, message: str) -> ChatLog:
    """
    Creates a new chat message in a session after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise NotFound("Chat session not found.")

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


def update_chat_log(user: User, log_id: int, data: dict) -> ChatLog:
    """
    Updates a chat log's details (e.g., is_important) after validating permissions.
    """
    try:
        log = ChatLog.objects.get(id=log_id)
    except ChatLog.DoesNotExist:
        raise NotFound("Chat log not found.")

    if log.user != user:
        raise PermissionDenied("You do not have permission to edit this chat log.")

    for attr, value in data.items():
        setattr(log, attr, value)
    log.save()
    return log


def delete_chat_log(user: User, log_id: int):
    """
    Deletes a chat log after validating user permissions.
    """
    try:
        log = ChatLog.objects.get(id=log_id)
    except ChatLog.DoesNotExist:
        raise NotFound("Chat log not found.")

    if log.user != user:
        raise PermissionDenied("You do not have permission to delete this chat log.")

    log.delete()


def create_voice_log(user: User, session_id: int, input_audio_url: str) -> VoiceLog:
    """
    Creates a new voice log for a session after validating user permissions.
    """
    try:
        session = ChatSession.objects.get(id=session_id)
    except ChatSession.DoesNotExist:
        raise NotFound("Chat session not found.")

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
