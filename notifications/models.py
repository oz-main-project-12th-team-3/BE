# notifications/models.py
from django.db import models
from django.conf import settings

# === 알림 유형 ===
class NotificationType(models.Model):
    code = models.CharField(max_length=50, unique=True)  # 알림 코드 (예: NEW_MESSAGE)
    description = models.TextField(blank=True)           # 알림 설명
    default_enabled = models.BooleanField(default=True) # 기본 활성 여부
    created_at = models.DateTimeField(auto_now_add=True) # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)    # 수정 시각

    def __str__(self):
        return self.code

# === 사용자 알림 설정 ===
class UserNotificationPreference(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)           # 대상 사용자
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)      # 알림 유형
    is_enabled = models.BooleanField(default=True)                                         # 수신 여부
    created_at = models.DateTimeField(auto_now_add=True)                                    # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)                                        # 수정 시각

    class Meta:
        unique_together = ('user', 'notification_type')  # 사용자+알림 유형 조합 유일

# === 알림 기록 ===
class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications'
    )                                                                                       # 받는 사람
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )                                                                                       # 보낸 사람 (선택)
    notification_type = models.ForeignKey(NotificationType, on_delete=models.CASCADE)       # 알림 유형
    title = models.CharField(max_length=255)                                               # 제목
    message = models.TextField(blank=True)                                                 # 상세 내용
    link = models.CharField(max_length=500, blank=True, null=True)                          # 관련 URL/화면
    is_read = models.BooleanField(default=False)                                           # 읽음 여부
    read_at = models.DateTimeField(null=True, blank=True)                                   # 읽은 시간
    created_at = models.DateTimeField(auto_now_add=True)                                    # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)                                        # 수정 시각

# === 예약 알림 ===
class ScheduleNotification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)           # 예약한 사용자
    notification = models.ForeignKey(Notification, on_delete=models.CASCADE)               # 연결된 알림
    scheduled_time = models.DateTimeField()                                                # 예정 발송 시간
    sent_at = models.DateTimeField(null=True, blank=True)                                   # 실제 발송 시간
    status = models.CharField(max_length=20, default='pending')                             # 상태 (pending, sent, failed)
    created_at = models.DateTimeField(auto_now_add=True)                                    # 생성 시각
    updated_at = models.DateTimeField(auto_now=True)                                        # 수정 시각
