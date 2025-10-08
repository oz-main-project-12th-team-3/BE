from django.db import migrations

def create_initial_notification_types(apps, schema_editor):
    """
    NotificationType 모델에 필수 초기 데이터를 삽입합니다.
    """
    # 마이그레이션 실행 시점의 'NotificationType' 모델 스냅샷을 가져옵니다.
    NotificationType = apps.get_model("notifications", "NotificationType")

    # === 삽입할 알림 유형 목록 ===
    initial_types = [
        {"code": "CHAT_MESSAGE", "description": "새로운 채팅 메시지", "default_enabled": True},
        {"code": "SCHEDULE_REMINDER", "description": "일정 알림 (예약)", "default_enabled": True},
        {"code": "PAYMENT_SUCCESS", "description": "결제 완료 알림", "default_enabled": True},
    ]

    for data in initial_types:
        # get_or_create를 사용하여 중복 삽입을 방지합니다.
        NotificationType.objects.get_or_create(
            code=data["code"],
            defaults={
                "description": data["description"],
                "default_enabled": data["default_enabled"]
            }
        )

def reverse_initial_notification_types(apps, schema_editor):
    """
    마이그레이션 롤백 시 삽입된 데이터를 삭제합니다.
    """
    NotificationType = apps.get_model("notifications", "NotificationType")
    NotificationType.objects.filter(
        code__in=["CHAT_MESSAGE", "SCHEDULE_REMINDER", "PAYMENT_SUCCESS"]
    ).delete()


class Migration(migrations.Migration):

    initial = False

    dependencies = [
        # 가장 최근 스키마 마이그레이션(0004)을 종속성으로 설정합니다.
        ('notifications', '0004_alter_notification_notification_type'),
    ]

    operations = [
        # 데이터 삽입 함수를 마이그레이션 작업으로 실행합니다.
        migrations.RunPython(
            create_initial_notification_types,
            reverse_code=reverse_initial_notification_types
        ),
    ]