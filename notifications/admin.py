from django.contrib import admin
from .models import NotificationType, UserNotificationPreference, Notification, ScheduleNotification

# ===================================================
# === 관리자 페이지 등록 (Notification 관련) ===
# ===================================================

# === 1. 알림 유형 관리 ===
@admin.register(NotificationType)
class NotificationTypeAdmin(admin.ModelAdmin):
    list_display = ('id', 'code', 'description', 'default_enabled', 'created_at', 'updated_at')  # 표시 필드
    search_fields = ('code', 'description')  # 검색 가능 필드
    list_filter = ('default_enabled',)      # 필터 옵션

# === 2. 사용자 알림 설정 관리 ===
@admin.register(UserNotificationPreference)
class UserNotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'notification_type', 'is_enabled', 'created_at', 'updated_at')
    list_filter = ('is_enabled',)
    search_fields = ('user__email', 'notification_type__code')

# === 3. Notification + 연결된 ScheduleNotification 안전 삭제 액션 ===
def delete_notification_with_schedule(modeladmin, request, queryset):
    """
    선택한 Notification과 연결된 ScheduleNotification을 함께 삭제
    """
    for notif in queryset:
        # 연결된 예약 알림도 함께 삭제
        notif.schedule_notification_set.all().delete()
        # Notification 삭제
        notif.delete()

delete_notification_with_schedule.short_description = "Notification + 연결된 예약 삭제"

# === 4. 알림 기록 관리 ===
@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'recipient', 'sender', 'notification_type', 'is_read', 'read_at', 'created_at')
    list_filter = ('is_read', 'notification_type')
    search_fields = ('title', 'message', 'recipient__email', 'sender__email')
    actions = [delete_notification_with_schedule, 'delete_selected']  # 체크박스 액션 + 기본 삭제

    # === 개별 삭제 버튼 활성화 ===
    def has_delete_permission(self, request, obj=None):
        return True  # 항상 삭제 가능

    # === 개별 삭제 시 연결된 ScheduleNotification도 삭제 ===
    def delete_model(self, request, obj):
        obj.schedule_notification_set.all().delete()
        obj.delete()

# === 5. 예약 알림 관리 ===
@admin.register(ScheduleNotification)
class ScheduleNotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'notification', 'scheduled_time', 'sent_at', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'notification__title')
