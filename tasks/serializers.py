from rest_framework import serializers
from .models import Task

class TaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = Task
        # 시리얼라이저에 포함할 필드
        fields = ['id', 'user', 'title', 'description', 'due_time', 'is_completed', 'created_at', 'updated_at']
        # 읽기 전용 필드
        read_only_fields = ['user', 'created_at', 'updated_at']
