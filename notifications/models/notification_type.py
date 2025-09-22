from django.db import models


# === 알림 유형 모델 ===
class NotificationType(models.Model):
    code = models.CharField(max_length=50, unique=True)  # 알림 코드 (예: NEW_MESSAGE)
    description = models.TextField(blank=True)  # 알림 설명
    default_enabled = models.BooleanField(default=True)  # 기본 활성 여부
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시각 자동 기록
    updated_at = models.DateTimeField(auto_now=True)  # 수정 시각 자동 기록

    def __str__(self):
        return self.code
