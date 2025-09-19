from django.contrib import admin
from .models import Schedule

@admin.register(Schedule)
class ScheduleAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'title',
        'user',
        'is_completed',
        'start_time',
        'end_time',
        'created_at',
        'updated_at',
    )
    list_display_links = ('title',)
    list_filter = ('is_completed', 'start_time', 'end_time', 'created_at')
    search_fields = ('title', 'description', 'user__email')
    ordering = ('-created_at',)
