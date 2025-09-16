from django.contrib.auth.models import AbstractUser
from django.db import models

class CustomUser(AbstractUser):
    # 나중에 필요한 필드를 여기에 추가할 수 있습니다.
    # 예: nickname = models.CharField(max_length=100, unique=True)
    pass