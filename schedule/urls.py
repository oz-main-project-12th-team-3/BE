# 서드파티 라이브러리
from django.urls import include, path
from rest_framework.routers import DefaultRouter

# 로컬 모듈
from .views import ScheduleViewSet

router = DefaultRouter()
router.register(r"schedules", ScheduleViewSet, basename="schedule")

urlpatterns = [
    path("", include(router.urls)),
]
