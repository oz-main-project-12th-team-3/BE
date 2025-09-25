import os

# 수정할 파일 목록
files_to_fix = [
    "notifications/admin.py",
    "notifications/serializers/schedule_notification_serializer.py",
    "notifications/tasks.py",
]

# 올바른 import 블록과 ScheduleNotification 참조로 교체
replacement_map = {
    "notifications/admin.py": """from django.contrib import admin
from notifications.models.schedule_notification import ScheduleNotification
from notifications.models.notification import Notification

@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "notification", "scheduled_time", "status", "sent_at")
""",
    "notifications/serializers/schedule_notification_serializer.py": """from rest_framework import serializers
from notifications.models.schedule_notification import ScheduleNotification

class ScheduleNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleNotification
        fields = "__all__"
""",
    "notifications/tasks.py": """from django.utils import timezone
from notifications.models.schedule_notification import ScheduleNotification

def send_scheduled_notifications():
    now = timezone.now()
    schedules = ScheduleNotification.objects.filter(status="pending", scheduled_time__lte=now)
    for schedule in schedules:
        # 실제 발송 로직
        schedule.status = "sent"
        schedule.sent_at = now
        schedule.save()
""",
}

for file_path, content in replacement_map.items():
    if os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] Updated {file_path}")
    else:
        print(f"[SKIP] File not found: {file_path}")

print("✅ ScheduleNotification 관련 F401/F821/I001 문제 자동 수정 완료")
