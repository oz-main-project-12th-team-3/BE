from django.apps import AppConfig


class TwoFactorWrapperConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "two_factor_wrapper"
    # 이 부분은 필수 아님: verbose_name = 'Two Factor URL Wrapper'
