from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _


class Sender(models.TextChoices):
    USER = 'user', _('User')
    AI = 'ai', _('AI')


class ChatSession(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.title} by {self.user.email}'


class ChatLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='chat_logs')
    message = models.TextField()
    sender = models.CharField(max_length=10, choices=Sender.choices)
    is_important = models.BooleanField(default=False)
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Message by {self.sender} in session {self.session.id}'


class VoiceLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='voice_logs')
    input_audio_url = models.URLField(max_length=1024)
    output_audio_url = models.URLField(max_length=1024, null=True, blank=True)
    transcribed_text = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Voice log for session {self.session.id}'