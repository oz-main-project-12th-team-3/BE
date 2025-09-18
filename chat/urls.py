from django.urls import path

from .views import (
    ChatMessageListCreateView,
    ChatSessionListCreateView,
    VoiceLogListCreateView,
)

urlpatterns = [
    path(
        "chat-sessions",
        ChatSessionListCreateView.as_view(),
        name="chat-sessions-list-create",
    ),
    path(
        "chat-messages",
        ChatMessageListCreateView.as_view(),
        name="chat-messages-list-create",
    ),
    path("voice-logs", VoiceLogListCreateView.as_view(), name="voice-logs-list-create"),
]
