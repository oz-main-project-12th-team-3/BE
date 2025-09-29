from django.core.exceptions import ValidationError

# 간단한 욕설 목록 예시 (실제 서비스에서는 더 포괄적인 목록 필요)
PROFANITY_LIST = ["바보", "멍청이", "나쁜말"]

def profanity_validator(value):
    """입력값에 욕설 목록에 있는 단어가 포함되어 있는지 확인합니다."""
    for word in PROFANITY_LIST:
        if word in value:
            raise ValidationError(f"부적절한 단어('{word}')가 포함되어 있습니다.")
