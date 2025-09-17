"""
URL configuration for tasks app.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TaskViewSet

# DRF DefaultRouter 생성
router = DefaultRouter()
router.register(r'tasks', TaskViewSet, basename='task')  # /tasks/ CRUD API

urlpatterns = [
    path('', include(router.urls)),  # /tasks/ CRUD API 포함
]
