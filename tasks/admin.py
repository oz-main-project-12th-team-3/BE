# Django 관리자 사이트 관련 모듈 import
from django.contrib import admin
# Task 모델 import
from .models import Task

# === Task 모델 관리자 등록 ===
@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    # 관리자 화면에서 표시할 컬럼 정의
    list_display = (
        'id',          # Task ID
        'title',       # 제목
        'user',        # 작성자 (User)
        'is_completed',# 완료 여부
        'due_time',    # 마감 시간
        'created_at',  # 생성일
        'updated_at',  # 수정일
    )

    # 클릭 시 상세 페이지로 이동할 컬럼
    list_display_links = ('title',)

    # 필터 사이드바에 표시할 필드
    list_filter = (
        'is_completed', # 완료 여부 필터
        'due_time',     # 마감 시간 필터
        'created_at',   # 생성일 필터
    )

    # 검색 기능에 포함할 필드
    search_fields = (
        'title',          # 제목 검색
        'description',    # 상세 내용 검색
        'user__email',    # 작성자 이메일 검색
    )

    # 기본 정렬 순서 (-created_at: 최신 순)
    ordering = ('-created_at',)
