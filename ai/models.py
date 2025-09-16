from django.db import models
from django.conf import settings


class RequestLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    request_body = models.TextField(null=True, blank=True)
    status_code = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.method} {self.endpoint} - {self.status_code}'


class ModelResult(models.Model):
    request = models.ForeignKey(RequestLog, on_delete=models.CASCADE, related_name='model_results')
    model_version = models.CharField(max_length=100)
    input_data = models.TextField(null=True, blank=True)
    output_data = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Model result for request {self.request.id}'


class PreprocessedData(models.Model):
    request = models.ForeignKey(RequestLog, on_delete=models.CASCADE, related_name='preprocessed_data')
    original_input = models.TextField(null=True, blank=True)
    cleaned_input = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Preprocessed data for request {self.request.id}'


class AICharacterState(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_character_state')
    memory = models.TextField(null=True, blank=True)
    last_interaction = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"AI character state for {self.user.email}"