"""Turns the router's call log into a cost report."""

from collections import Counter, defaultdict

from pydantic import BaseModel

from ai_discovery.llm.types import CallRecord, ModelSpec


class CostReport(BaseModel):
    total_calls: int
    calls_by_tier: dict[str, int]
    escalated_calls: int
    outcomes: dict[str, int]
    total_cost_usd: float
    all_large_cost_usd: float  # estimate: the same requests, all sent to the large model
    cost_by_task: dict[str, float]

    @property
    def saving_usd(self) -> float:
        return self.all_large_cost_usd - self.total_cost_usd


def build_cost_report(calls: list[CallRecord], large: ModelSpec) -> CostReport:
    tiers: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    cost_by_task: dict[str, float] = defaultdict(float)
    all_large = 0.0
    escalated = 0

    for call in calls:
        tiers[call.tier.value] += 1
        outcomes[call.outcome] += 1
        cost_by_task[call.task] += call.cost_usd

        if call.escalated_from is not None:
            escalated += 1
        elif call.input_tokens or call.output_tokens:
            # One entry per original request. Escalated retries are not extra requests.
            all_large += large.cost(call.input_tokens, call.output_tokens)

    return CostReport(
        total_calls=len(calls),
        calls_by_tier=dict(tiers),
        escalated_calls=escalated,
        outcomes=dict(outcomes),
        total_cost_usd=sum(call.cost_usd for call in calls),
        all_large_cost_usd=all_large,
        cost_by_task=dict(cost_by_task),
    )