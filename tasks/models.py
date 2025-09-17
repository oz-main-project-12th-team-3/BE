from django.db import models
from django.conf import settings  # ✅ AUTH_USER_MODEL 사용


class Task(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # User 대신 안전하게 설정 참조
        on_delete=models.CASCADE,
        related_name="tasks",
        verbose_name="사용자",
    )
    title = models.CharField(max_length=255, verbose_name="제목")
    description = models.TextField(blank=True, null=True, verbose_name="상세 내용")
    due_time = models.DateTimeField(blank=True, null=True, verbose_name="마감 시간")
    is_completed = models.BooleanField(default=False, verbose_name="완료 여부")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일")

    class Meta:
        verbose_name = "태스크"
        verbose_name_plural = "태스크 목록"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({'완료' if self.is_completed else '미완료'})"
