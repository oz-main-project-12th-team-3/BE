from django.conf import settings
from django.db import models

# The following logging models (RequestLog, ModelResult, PreprocessedData) have been
# removed in favor of a structured logging system (e.g., AWS CloudWatch) to avoid
# database overhead.


class AICharacterState(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_character_state",
    )
    memory = models.TextField(null=True, blank=True)
    last_interaction = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI character state for {self.user.email}"
