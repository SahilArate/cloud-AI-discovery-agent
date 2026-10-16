"""Builds the LLM router from settings. Returns None when no API key is configured."""

from ai_discovery.config import Settings
from ai_discovery.llm.providers import GroqProvider
from ai_discovery.llm.router import LLMRouter
from ai_discovery.llm.types import ModelSpec, ModelTier


def build_model_specs(settings: Settings) -> tuple[ModelSpec, ModelSpec]:
    small = ModelSpec(
        tier=ModelTier.SMALL,
        model_name=settings.small_model_name,
        input_price_per_million=settings.small_input_price_per_million,
        output_price_per_million=settings.small_output_price_per_million,
    )
    large = ModelSpec(
        tier=ModelTier.LARGE,
        model_name=settings.large_model_name,
        input_price_per_million=settings.large_input_price_per_million,
        output_price_per_million=settings.large_output_price_per_million,
    )
    return small, large


def build_router(settings: Settings) -> LLMRouter | None:
    """No key means no LLM. The scan still works, ambiguous items stay in review."""
    if not settings.groq_api_key:
        return None
    small, large = build_model_specs(settings)
    return LLMRouter(
        GroqProvider(settings.groq_api_key), small, large, budget_usd=settings.llm_budget_usd
    )