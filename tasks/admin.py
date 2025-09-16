from django.contrib import admin
from .models import Task

@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_completed', 'due_time', 'created_at')
    list_filter = ('is_completed', 'due_time')
    search_fields = ('title', 'description', 'user__email')
    ordering = ('-created_at',)
