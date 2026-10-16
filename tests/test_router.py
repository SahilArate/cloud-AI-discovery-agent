"""Router tests: a fake provider stands in for Groq, so nothing here costs money."""

import pytest

from ai_discovery.llm.providers import LLMProvider, ProviderError
from ai_discovery.llm.router import MIN_OUTPUT_TOKENS, LLMRouter
from ai_discovery.llm.types import LLMRequest, LLMResponse, ModelSpec, ModelTier

SMALL = ModelSpec(
    tier=ModelTier.SMALL,
    model_name="fake-small",
    input_price_per_million=1.0,
    output_price_per_million=1.0,
)
LARGE = ModelSpec(
    tier=ModelTier.LARGE,
    model_name="fake-large",
    input_price_per_million=10.0,
    output_price_per_million=10.0,
)


class FakeProvider(LLMProvider):
    """Replays scripted replies per model. A ProviderError instance is raised, not returned."""

    def __init__(self, replies: dict[str, list]) -> None:
        self._replies = replies
        self.requests: list[tuple[str, LLMRequest]] = []

    def complete(self, request: LLMRequest, model_name: str) -> LLMResponse:
        self.requests.append((model_name, request))
        reply = self._replies[model_name].pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResponse(
            text=reply,
            model_name=model_name,
            input_tokens=1000,
            output_tokens=1000,
            latency_ms=5,
        )


def _request() -> LLMRequest:
    return LLMRequest(task="inspect_resource", system_prompt="s", user_prompt="u")


def _accept_yes(text: str) -> str | None:
    return text if text == "yes" else None


def _router(provider: FakeProvider, budget_usd: float = 1.0) -> LLMRouter:
    return LLMRouter(provider, SMALL, LARGE, budget_usd=budget_usd)


def test_small_model_is_tried_first_and_used_when_output_is_valid():
    provider = FakeProvider({"fake-small": ["yes"], "fake-large": []})
    router = _router(provider)

    result = router.run(_request(), _accept_yes)

    assert result == "yes"
    assert [model for model, _ in provider.requests] == ["fake-small"]
    assert router.calls[0].outcome == "ok"
    assert router.calls[0].escalated_from is None


def test_invalid_output_escalates_to_the_large_model():
    provider = FakeProvider({"fake-small": ["garbage"], "fake-large": ["yes"]})
    router = _router(provider)

    result = router.run(_request(), _accept_yes)

    assert result == "yes"
    assert [call.tier for call in router.calls] == [ModelTier.SMALL, ModelTier.LARGE]
    assert router.calls[0].outcome == "invalid_output"
    assert router.calls[1].escalated_from == ModelTier.SMALL


def test_both_tiers_failing_returns_none():
    provider = FakeProvider({"fake-small": ["bad"], "fake-large": ["worse"]})

    assert _router(provider).run(_request(), _accept_yes) is None


def test_provider_error_does_not_escalate():
    provider = FakeProvider({"fake-small": [ProviderError("Timeout")], "fake-large": ["yes"]})
    router = _router(provider)

    result = router.run(_request(), _accept_yes)

    assert result is None
    assert [model for model, _ in provider.requests] == ["fake-small"]
    assert router.calls[0].outcome == "provider_error"


def test_budget_blocks_calls_once_spent():
    # Each small call costs (1000 + 1000) * $1 / 1M = $0.002, over this tiny budget.
    provider = FakeProvider({"fake-small": ["bad"], "fake-large": ["yes"]})
    router = _router(provider, budget_usd=0.001)

    result = router.run(_request(), _accept_yes)

    assert result is None
    outcomes = [call.outcome for call in router.calls]
    assert outcomes == ["invalid_output", "budget_blocked"]
    assert len(provider.requests) == 1  # the blocked call never reached the provider


def test_spent_usd_adds_up_the_call_costs():
    provider = FakeProvider({"fake-small": ["bad"], "fake-large": ["yes"]})
    router = _router(provider)

    router.run(_request(), _accept_yes)

    # small: 2000 tokens at $1/M = 0.002; large: 2000 tokens at $10/M = 0.02
    assert router.spent_usd == pytest.approx(0.022)


def test_output_token_limit_has_a_safe_minimum():
    provider = FakeProvider({"fake-small": ["yes"], "fake-large": []})
    request = LLMRequest(task="t", system_prompt="s", user_prompt="u", max_output_tokens=5)

    _router(provider).run(request, _accept_yes)

    assert provider.requests[0][1].max_output_tokens == MIN_OUTPUT_TOKENS


def test_call_log_holds_no_prompt_text():
    provider = FakeProvider({"fake-small": ["yes"], "fake-large": []})
    router = _router(provider)

    router.run(
        LLMRequest(task="t", system_prompt="SECRET-SYSTEM", user_prompt="SECRET-USER"),
        _accept_yes,
    )

    dumped = router.calls[0].model_dump_json()
    assert "SECRET-SYSTEM" not in dumped
    assert "SECRET-USER" not in dumped