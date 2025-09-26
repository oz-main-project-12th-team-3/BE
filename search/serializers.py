from rest_framework import serializers

from .models import SearchLog


class SearchLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchLog
        fields = [
            "id",
            "user",
            "keyword",
            "search_type",
            "result_count",
            "clicked_result_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
