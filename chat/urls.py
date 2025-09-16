from django.urls import path
from .views import (
    ChatSessionListCreateView,
    ChatMessageListCreateView,
    VoiceLogListCreateView,
)

urlpatterns = [
    path('session', ChatSessionListCreateView.as_view(), name='chat-session-list-create'),
    path('message', ChatMessageListCreateView.as_view(), name='chat-message-list-create'),
    path('voicelog', VoiceLogListCreateView.as_view(), name='voicelog-list-create'),
]
