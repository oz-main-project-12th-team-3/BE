from django.conf import settings
from openai import OpenAI

client = OpenAI(
    api_key=settings.GEMINI_API_KEY,
    base_url=getattr(
        settings,
        "GEMINI_API_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
)
