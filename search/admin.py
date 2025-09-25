from django.contrib import admin
from .models import SearchLog

@admin.register(SearchLog)
class SearchLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "keyword", "search_type", "result_count", "clicked_result_id", "created_at")
    list_filter = ("search_type", "created_at")
    search_fields = ("keyword", "user__email")
    ordering = ("-created_at",)
