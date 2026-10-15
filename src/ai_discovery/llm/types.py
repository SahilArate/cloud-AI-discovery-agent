"""Shapes shared by the LLM router and its providers."""

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ModelTier(str, Enum):
    SMALL = "small"  # cheap and fast, tried first
    LARGE = "large"  # stronger and pricier, only when the small one isn't enough


class ModelSpec(BaseModel):
    """One concrete model and what it costs. Prices come from config, not code."""

    tier: ModelTier
    model_name: str
    input_price_per_million: float  # USD per 1M input tokens
    output_price_per_million: float  # USD per 1M output tokens

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens * self.input_price_per_million
            + output_tokens * self.output_price_per_million
        ) / 1_000_000


class LLMRequest(BaseModel):
    task: str  # e.g. "inspect_resource", so cost can be reported per task
    system_prompt: str
    user_prompt: str
    max_output_tokens: int = 500


class LLMResponse(BaseModel):
    text: str
    model_name: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


CallOutcome = Literal["ok", "invalid_output", "provider_error", "budget_blocked"]


class CallRecord(BaseModel):
    """One line in the cost report: what was asked, which model, what it cost."""

    task: str
    tier: ModelTier
    model_name: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    outcome: CallOutcome
    escalated_from: ModelTier | None = None  # set when this call is a retry on a bigger model
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))