"""Database tables. Observations are append-only: new scans add rows, never edit old ones."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_discovery.db.base import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class ScanRun(Base):
    """One execution of a discovery scan."""

    __tablename__ = "scan_runs"

    scan_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: _new_id("scan")
    )
    scan_mode: Mapped[str] = mapped_column(String(16))  # "mock" or "live"
    status: Mapped[str] = mapped_column(String(16), default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resources_seen: Mapped[int] = mapped_column(Integer, default=0)


class AIAsset(Base):
    """Stable identity of a discovered resource. One row per asset, across all scans."""

    __tablename__ = "ai_assets"

    asset_key: Mapped[str] = mapped_column(String(512), primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    account_id: Mapped[str] = mapped_column(String(64))
    native_id: Mapped[str] = mapped_column(String(512))
    name: Mapped[str] = mapped_column(String(256))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

class AssetObservation(Base):
    """What one scan saw about one asset. Never updated after insert."""

    __tablename__ = "asset_observations"

    observation_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: _new_id("obs")
    )
    asset_key: Mapped[str] = mapped_column(ForeignKey("ai_assets.asset_key"), index=True)
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan_runs.scan_id"), index=True)

    # Is it AI? Is it being used? Kept as separate columns on purpose.
    ai_verdict: Mapped[str] = mapped_column(String(24))
    activity_status: Mapped[str] = mapped_column(String(24))
    reasoning: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[str] = mapped_column(String(16), default="rules")
    llm_confidence: Mapped[float | None] = mapped_column()
    review_required: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_evidence: Mapped[list] = mapped_column(JSONB, default=list)

    # Ownership: the value and where it came from
    owner: Mapped[str | None] = mapped_column(String(256))
    owner_source: Mapped[str] = mapped_column(String(24), default="unknown")

    # Usage: a count plus the window it was measured over, not a vague label
    usage_count: Mapped[int | None] = mapped_column(Integer)
    usage_window_days: Mapped[int | None] = mapped_column(Integer)

    region: Mapped[str] = mapped_column(String(64))
    hosting_type: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)

    # Approval is a separate question from the AI verdict
    approval_status: Mapped[str] = mapped_column(String(24), default="not_assessed")
    risk_tier: Mapped[str] = mapped_column(String(16), default="unassessed")

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)

    evidence: Mapped[list["EvidenceRecord"]] = relationship(back_populates="observation")


class EvidenceRecord(Base):
    """One clue behind an observation's verdict."""

    __tablename__ = "evidence_records"

    evidence_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    observation_id: Mapped[str] = mapped_column(
        ForeignKey("asset_observations.observation_id"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(32))
    strength: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    observation: Mapped["AssetObservation"] = relationship(back_populates="evidence")

class GovernanceReview(Base):
    """A human decision about an asset. New decisions add rows, old ones stay as history."""

    __tablename__ = "governance_reviews"

    review_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: _new_id("rev")
    )
    asset_key: Mapped[str] = mapped_column(ForeignKey("ai_assets.asset_key"), index=True)
    observation_id: Mapped[str | None] = mapped_column(
        ForeignKey("asset_observations.observation_id")
    )
    status: Mapped[str] = mapped_column(String(16), default="pending_review")
    reviewer: Mapped[str | None] = mapped_column(String(256))
    reason: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    reason_codes: Mapped[list] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ScanScopeResult(Base):
    """Coverage for one scope (provider, account, region, service) within one scan."""

    __tablename__ = "scan_scope_results"

    scope_result_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: _new_id("scope")
    )
    scan_id: Mapped[str] = mapped_column(ForeignKey("scan_runs.scan_id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    account_id: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(64))
    service: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    resources_discovered: Mapped[int] = mapped_column(Integer, default=0)
    resources_inspected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)