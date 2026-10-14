"""A single piece of evidence about a resource, with where it came from."""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ai_discovery.models.enums import EvidenceStrength, EvidenceType


def _new_evidence_id() -> str:
    return f"ev-{uuid.uuid4().hex[:10]}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=_new_evidence_id)
    asset_key: str  # links back to Resource.asset_key
    evidence_type: EvidenceType
    strength: EvidenceStrength
    source: str  # where we saw it, e.g. "lambda_config", "cloudwatch_metrics"
    detail: str  # short, human-readable, never a secret value
    observed_at: datetime = Field(default_factory=_utc_now)