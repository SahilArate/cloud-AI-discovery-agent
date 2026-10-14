"""The classification result for one resource: verdict, activity, and why."""

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ai_discovery.models.enums import ActivityStatus, AIVerdict
from ai_discovery.models.evidence import Evidence


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Finding(BaseModel):
    asset_key: str
    verdict: AIVerdict
    activity_status: ActivityStatus = ActivityStatus.ACTIVITY_UNKNOWN
    evidence: list[Evidence] = Field(default_factory=list)

    reasoning: str  # one or two sentences a reviewer can read
    missing_evidence: list[str] = Field(default_factory=list)
    review_required: bool = False

    decided_by: Literal["rules", "llm_inspector"] = "rules"
    # Only set when the LLM decided. Model-reported, not a calibrated probability.
    llm_confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    decided_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def _ai_verdicts_need_evidence(self) -> "Finding":
        needs_evidence = {AIVerdict.AI_CONFIRMED, AIVerdict.AI_SUSPECTED}
        if self.verdict in needs_evidence and not self.evidence:
            raise ValueError(f"{self.verdict.value} requires at least one evidence record")
        return self