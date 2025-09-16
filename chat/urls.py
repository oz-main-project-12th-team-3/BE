from django.urls import path
from .views import ChatSessionListCreateView, ChatMessageListCreateView

urlpatterns = [
    path('session', ChatSessionListCreateView.as_view(), name='chat-session-list-create'),
    path('message', ChatMessageListCreateView.as_view(), name='chat-message-list-create'),
]
