from rest_framework import serializers

from users.validators import profanity_validator

from .models import Schedule


class ScheduleSerializer(serializers.ModelSerializer):
    title = serializers.CharField(validators=[profanity_validator])
    description = serializers.CharField(
        validators=[profanity_validator], required=False
    )

    class Meta:
        model = Schedule
        fields = [
            "id",
            "user",
            "title",
            "description",
            "start_time",
            "end_time",
            "is_completed",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "created_at", "updated_at"]
