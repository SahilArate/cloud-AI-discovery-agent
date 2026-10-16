"""Picks a model tier per request, escalates when output is unusable, enforces a budget."""

from collections.abc import Callable
from typing import TypeVar

from ai_discovery.llm.providers import LLMProvider, ProviderError
from ai_discovery.llm.types import (
    CallOutcome,
    CallRecord,
    LLMRequest,
    ModelSpec,
    ModelTier,
)

T = TypeVar("T")

# Reasoning models spend output tokens thinking, so tiny limits can return empty text.
MIN_OUTPUT_TOKENS = 400


class LLMRouter:
    def __init__(
        self,
        provider: LLMProvider,
        small: ModelSpec,
        large: ModelSpec,
        budget_usd: float = 0.50,
    ) -> None:
        self._provider = provider
        self._models = {ModelTier.SMALL: small, ModelTier.LARGE: large}
        self._budget_usd = budget_usd
        self.calls: list[CallRecord] = []

    @property
    def spent_usd(self) -> float:
        return sum(call.cost_usd for call in self.calls)

    def run(self, request: LLMRequest, validate: Callable[[str], T | None]) -> T | None:
        """Try the small model, then the large one. Returns the validated result or None.

        validate takes the raw text and returns a parsed value, or None if unusable.
        """
        request = request.model_copy(
            update={"max_output_tokens": max(request.max_output_tokens, MIN_OUTPUT_TOKENS)}
        )

        result = self._attempt(request, ModelTier.SMALL, validate, escalated_from=None)
        if result is not None:
            return result

        # Only unusable output is worth a stronger model. A provider outage or a
        # blocked budget would just fail again on the large tier.
        if self.calls[-1].outcome != "invalid_output":
            return None
        return self._attempt(request, ModelTier.LARGE, validate, escalated_from=ModelTier.SMALL)

    def _attempt(
        self,
        request: LLMRequest,
        tier: ModelTier,
        validate: Callable[[str], T | None],
        escalated_from: ModelTier | None,
    ) -> T | None:
        spec = self._models[tier]

        if self.spent_usd >= self._budget_usd:
            self._log(request, spec, "budget_blocked", escalated_from)
            return None

        try:
            response = self._provider.complete(request, spec.model_name)
        except ProviderError:
            self._log(request, spec, "provider_error", escalated_from)
            return None

        parsed = validate(response.text)
        outcome: CallOutcome = "ok" if parsed is not None else "invalid_output"
        self._log(
            request,
            spec,
            outcome,
            escalated_from,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
        )
        return parsed

    def _log(
        self,
        request: LLMRequest,
        spec: ModelSpec,
        outcome: CallOutcome,
        escalated_from: ModelTier | None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
    ) -> None:
        self.calls.append(
            CallRecord(
                task=request.task,
                tier=spec.tier,
                model_name=spec.model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=spec.cost(input_tokens, output_tokens),
                latency_ms=latency_ms,
                outcome=outcome,
                escalated_from=escalated_from,
            )
        )