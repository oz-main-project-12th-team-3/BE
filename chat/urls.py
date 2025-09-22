from django.urls import path

from .views import (
    ChatMessageListCreateView,
    ChatSessionListCreateView,
    # TODO: Add ChatSessionDetailView for update/delete
)

urlpatterns = [
    path(
        "chat-sessions/",
        ChatSessionListCreateView.as_view(),
        name="chat-session-list-create",
    ),
    # path(
    #     "chat-sessions/<int:session_id>/",
    #     ChatSessionDetailView.as_view(),
    #     name="chat-session-detail",
    # ), # TODO: Implement
    path(
        "chat-sessions/<int:session_id>/messages/",
        ChatMessageListCreateView.as_view(),
        name="chat-message-list-create",
    ),
]