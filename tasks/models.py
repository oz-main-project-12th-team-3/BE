from django.db import models
from django.conf import settings

class Task(models.Model):
    # Task를 소유한 사용자
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tasks',
        verbose_name='사용자'
    )
    # Task 제목
    title = models.CharField(max_length=255, verbose_name='제목')
    # Task 상세 내용 (선택)
    description = models.TextField(blank=True, null=True, verbose_name='상세 내용')
    # Task 마감 시간 (선택)
    due_time = models.DateTimeField(blank=True, null=True, verbose_name='마감 시간')
    # Task 완료 여부
    is_completed = models.BooleanField(default=False, verbose_name='완료 여부')
    # 생성 시각 자동 기록
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='생성 시각')
    # 수정 시각 자동 기록
    updated_at = models.DateTimeField(auto_now=True, verbose_name='수정 시각')

    class Meta:
        # 생성일 기준 내림차순 정렬
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({'완료' if self.is_completed else '미완료'})"
