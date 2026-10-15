"""Model providers. The router talks to the interface, never to a vendor SDK directly."""

import time
from abc import ABC, abstractmethod

from openai import OpenAI

from ai_discovery.llm.types import LLMRequest, LLMResponse


class ProviderError(Exception):
    """Raised when the provider call fails. Carries no prompt text."""


class LLMProvider(ABC):
    @abstractmethod
    def complete(self, request: LLMRequest, model_name: str) -> LLMResponse:
        """Send one request to one model and return the text plus token counts."""


class GroqProvider(LLMProvider):
    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str, timeout_seconds: float = 30.0) -> None:
        if not api_key:
            raise ProviderError("GROQ_API_KEY is not set")
        self._client = OpenAI(
            api_key=api_key, base_url=self.BASE_URL, timeout=timeout_seconds, max_retries=1
        )

    def complete(self, request: LLMRequest, model_name: str) -> LLMResponse:
        started = time.monotonic()
        try:
            response = self._client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                max_tokens=request.max_output_tokens,
                temperature=0,
            )
        except Exception as error:
            # Only the error type is kept, in case the message echoes the prompt.
            raise ProviderError(type(error).__name__) from error

        usage = response.usage
        return LLMResponse(
            text=response.choices[0].message.content or "",
            model_name=model_name,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
            latency_ms=int((time.monotonic() - started) * 1000),
        )