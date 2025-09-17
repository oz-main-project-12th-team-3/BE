from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet

# RESTful 라우터 생성
router = DefaultRouter()
# /tasks/ 경로에 TaskViewSet 등록
router.register(r'tasks', TaskViewSet, basename='task')

urlpatterns = [
    path('', include(router.urls)),  # 라우터 포함
]
