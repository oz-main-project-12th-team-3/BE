from django.urls import path

from .views import (
    ChatMessageListCreateView,
    ChatMessageSearchView,
    ChatSessionDetailView,
    ChatSessionListCreateView,
)

urlpatterns = [
    path(
        "chat-sessions/",
        ChatSessionListCreateView.as_view(),
        name="chat-session-list-create",
    ),
    path(
        "chat-sessions/<int:session_id>/",
        ChatSessionDetailView.as_view(),
        name="chat-session-detail",
    ),
    path(
        "chat-sessions/<int:session_id>/messages/",
        ChatMessageListCreateView.as_view(),
        name="chat-message-list-create",
    ),
    path(
        "chat/messages/search/",
        ChatMessageSearchView.as_view(),
        name="chat-message-search",
    ),
]
