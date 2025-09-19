from django.conf import settings
from django.db import models


class Schedule(models.Model):
    # 일정 소유자
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="사용자",
    )
    # 일정 제목
    title = models.CharField(max_length=255, verbose_name="제목")
    # 일정 상세 내용 (선택)
    description = models.TextField(blank=True, null=True, verbose_name="상세 내용")
    # 일정 시작/종료 시간
    start_time = models.DateTimeField(blank=True, null=True, verbose_name="시작 시간")
    end_time = models.DateTimeField(blank=True, null=True, verbose_name="종료 시간")
    # 완료 여부
    is_completed = models.BooleanField(default=False, verbose_name="완료 여부")
    # 생성/수정 시각 자동 기록
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성 시각")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정 시각")

    class Meta:
        ordering = ["-created_at"]  # 생성일 기준 내림차순 정렬

    def __str__(self):
        return f"{self.title} ({'완료' if self.is_completed else '미완료'})"
