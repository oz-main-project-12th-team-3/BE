from django.urls import path

from .views import AITextChatView, AIVoiceChatView

urlpatterns = [
    path("text-chat/", AITextChatView.as_view(), name="ai-text-chat"),
    path("voice-chat/", AIVoiceChatView.as_view(), name="ai-voice-chat"),
]
