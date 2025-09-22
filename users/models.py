import hashlib
import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
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
    ROLE_CHOICES = [("admin", "Admin"), ("user", "User")]
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default="user")
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    login_fail_count = models.IntegerField(default=0)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def is_account_locked(self):
        return self.account_locked_until and self.account_locked_until > timezone.now()


class Token(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_tokens")
    refresh_token_id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="UUID로 생성된 고유한 리프레시 토큰 ID",
    )
    refresh_token_hash = models.CharField(
        max_length=64,
        unique=True,
        help_text="JWT Refresh Token SHA256 Hash",
        default="",
        blank=True,
    )
    issued_at = models.DateTimeField(help_text="토큰 발급일시")
    expires_at = models.DateTimeField(help_text="토큰 만료일시")
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    is_blacklisted = models.BooleanField(
        default=False, help_text="토큰이 무효화(블랙리스트)되었는지 여부"
    )
    parent_token = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_tokens",
        help_text="이 토큰을 발급하는 데 사용된 이전 토큰 (토큰 회전 정책)",
    )

    def set_refresh_token(self, refresh_token_plain):
        self.refresh_token_hash = hashlib.sha256(
            refresh_token_plain.encode("utf-8")
        ).hexdigest()

    def check_refresh_token(self, refresh_token_plain):
        return (
            self.refresh_token_hash
            == hashlib.sha256(refresh_token_plain.encode("utf-8")).hexdigest()
        )


class UserProfile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="user_profile"
    )
    nickname = models.CharField(max_length=100)
    profile_image_url = models.URLField(null=True, blank=True)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)


# @receiver(post_save, sender=User)
# def create_user_profile(sender, instance, created, **kwargs):
#     if created and not hasattr(instance, "user_profile"):
#         UserProfile.objects.create(user=instance, nickname=instance.email.split('@')[0])
