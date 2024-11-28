from django.conf import settings
from openai import AsyncOpenAI

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
