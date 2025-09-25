from django.db import models
from django.conf import settings

class SearchLog(models.Model):
    """
    사용자 검색 로그 모델
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # users.User 모델 참조
        on_delete=models.CASCADE,
        related_name="search_logs",
        null=True,  # 익명 사용자의 검색도 저장 가능
        blank=True
    )
    keyword = models.CharField(max_length=255, verbose_name="검색어")
    search_type = models.CharField(max_length=50, null=True, blank=True, verbose_name="검색 유형")
    result_count = models.IntegerField(default=0, verbose_name="검색 결과 수")
    clicked_result_id = models.IntegerField(null=True, blank=True, verbose_name="클릭된 결과 ID")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="생성일시")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="수정일시")

    class Meta:
        db_table = "search_log"
        verbose_name = "검색 로그"
        verbose_name_plural = "검색 로그"

    def __str__(self):
        return f"{self.keyword} ({self.user})"
