from anthropic import AsyncAnthropic
from django.conf import settings
from openai import AsyncOpenAI

anthropic_client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
