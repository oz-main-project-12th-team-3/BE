from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("이메일은 필수 입력 항목입니다.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", "admin")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("슈퍼유저는 is_staff=True여야 합니다.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("슈퍼유저는 is_superuser=True여야 합니다.")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ("admin", "Admin"),
        ("user", "User"),
        ("moderator", "Moderator"),
    ]
    email = models.EmailField(unique=True)
    password_salt = models.CharField(max_length=255, null=True, blank=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    login_fail_count = models.IntegerField(default=0)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    account_lockout_en = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email


class Token(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    refresh_token = models.CharField(max_length=512)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    nickname = models.CharField(max_length=100)
    profile_image_url = models.URLField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
