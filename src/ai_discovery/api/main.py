"""HTTP API: health check and the current AI inventory."""

from collections.abc import Iterator
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from ai_discovery.db.tables import (
    AIAsset,
    AssetObservation,
    GovernanceReview,
    ScanRun,
    ScanScopeResult,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AIAsset, AssetObservation, ScanRun, ScanScopeResult
from sqlalchemy.dialects.postgresql import distinct_on
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints
from ai_discovery.models.enums import ReviewStatus

app = FastAPI(title="AI Discovery Agent", version="0.1.0")


def get_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


class InventoryItem(BaseModel):
    asset_key: str
    name: str
    ai_verdict: str
    activity_status: str
    approval_status: str
    risk_tier: str
    owner: str | None
    owner_source: str
    region: str
    hosting_type: str | None
    review_required: bool
    decided_by: str
    reasoning: str
    first_seen: datetime
    last_seen: datetime


@app.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, str]:
    session.execute(text("select 1"))
    return {"status": "ok"}

@app.get("/inventory", response_model=list[InventoryItem])
def inventory(
    include_missing: bool = False, session: Session = Depends(get_session)
) -> list[InventoryItem]:
    """AI assets seen in the latest scan. include_missing=true adds older, unseen ones."""
    query = (
        select(AssetObservation, AIAsset)
        .join(AIAsset, AIAsset.asset_key == AssetObservation.asset_key)
        .ext(distinct_on(AssetObservation.asset_key))
        .order_by(AssetObservation.asset_key, AssetObservation.observed_at.desc())
    )
    if not include_missing:
        latest = _latest_scans(session, 1)
        if not latest:
            return []
        query = query.where(AssetObservation.scan_id == latest[0].scan_id)

    rows = session.execute(query).all()
    return [
        InventoryItem(
            asset_key=asset.asset_key,
            name=asset.name,
            ai_verdict=obs.ai_verdict,
            activity_status=obs.activity_status,
            approval_status=obs.approval_status,
            risk_tier=obs.risk_tier,
            owner=obs.owner,
            owner_source=obs.owner_source,
            region=obs.region,
            hosting_type=obs.hosting_type,
            review_required=obs.review_required,
            decided_by=obs.decided_by,
            reasoning=obs.reasoning,
            first_seen=asset.first_seen,
            last_seen=asset.last_seen,
        )
        for obs, asset in rows
    ]

class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: str
    strength: str
    source: str
    detail: str


class ObservationItem(BaseModel):
    observation_id: str
    scan_id: str
    observed_at: datetime
    ai_verdict: str
    activity_status: str
    approval_status: str
    risk_tier: str
    owner: str | None
    owner_source: str
    usage_count: int | None
    usage_window_days: int | None
    decided_by: str
    review_required: bool
    reasoning: str
    missing_evidence: list[str]
    evidence: list[EvidenceItem]


class AssetDetail(BaseModel):
    asset_key: str
    name: str
    provider: str
    account_id: str
    native_id: str
    first_seen: datetime
    last_seen: datetime
    observations: list[ObservationItem]  # newest first


@app.get("/assets/{asset_key:path}", response_model=AssetDetail)
def asset_detail(asset_key: str, session: Session = Depends(get_session)) -> AssetDetail:
    asset = session.get(AIAsset, asset_key)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    observations = session.scalars(
        select(AssetObservation)
        .where(AssetObservation.asset_key == asset_key)
        .order_by(AssetObservation.observed_at.desc())
    ).all()

    return AssetDetail(
        asset_key=asset.asset_key,
        name=asset.name,
        provider=asset.provider,
        account_id=asset.account_id,
        native_id=asset.native_id,
        first_seen=asset.first_seen,
        last_seen=asset.last_seen,
        observations=[
            ObservationItem(
                observation_id=obs.observation_id,
                scan_id=obs.scan_id,
                observed_at=obs.observed_at,
                ai_verdict=obs.ai_verdict,
                activity_status=obs.activity_status,
                approval_status=obs.approval_status,
                risk_tier=obs.risk_tier,
                owner=obs.owner,
                owner_source=obs.owner_source,
                usage_count=obs.usage_count,
                usage_window_days=obs.usage_window_days,
                decided_by=obs.decided_by,
                review_required=obs.review_required,
                reasoning=obs.reasoning,
                missing_evidence=obs.missing_evidence,
                evidence=[
                    EvidenceItem(
                        evidence_id=item.evidence_id,
                        evidence_type=item.evidence_type,
                        strength=item.strength,
                        source=item.source,
                        detail=item.detail,
                    )
                    for item in obs.evidence
                ],
            )
            for obs in observations
        ],
    )


class ScopeItem(BaseModel):
    region: str
    service: str
    status: str
    resources_discovered: int
    resources_inspected: int
    errors: list[dict]


class CoverageReport(BaseModel):
    scan_id: str
    scan_status: str
    started_at: datetime
    scopes_total: int
    scopes_complete: int
    scopes_with_gaps: int
    scopes: list[ScopeItem]


def _latest_scans(session: Session, count: int) -> list[ScanRun]:
    return list(
        session.scalars(select(ScanRun).order_by(ScanRun.started_at.desc()).limit(count)).all()
    )


@app.get("/coverage/latest", response_model=CoverageReport)
def latest_coverage(session: Session = Depends(get_session)) -> CoverageReport:
    scans = _latest_scans(session, 1)
    if not scans:
        raise HTTPException(status_code=404, detail="no scans yet")
    scan = scans[0]

    scopes = session.scalars(
        select(ScanScopeResult)
        .where(ScanScopeResult.scan_id == scan.scan_id)
        .order_by(ScanScopeResult.region, ScanScopeResult.service)
    ).all()
    complete = sum(1 for scope in scopes if scope.status == "complete")

    return CoverageReport(
        scan_id=scan.scan_id,
        scan_status=scan.status,
        started_at=scan.started_at,
        scopes_total=len(scopes),
        scopes_complete=complete,
        scopes_with_gaps=len(scopes) - complete,
        scopes=[
            ScopeItem(
                region=scope.region,
                service=scope.service,
                status=scope.status,
                resources_discovered=scope.resources_discovered,
                resources_inspected=scope.resources_inspected,
                errors=scope.errors,
            )
            for scope in scopes
        ],
    )


class ChangeReport(BaseModel):
    latest_scan_id: str
    previous_scan_id: str | None
    new_assets: list[str]
    missing_assets: list[str]
    note: str


def _assets_seen_in(session: Session, scan_id: str) -> set[str]:
    return set(
        session.scalars(
            select(AssetObservation.asset_key).where(AssetObservation.scan_id == scan_id)
        ).all()
    )


@app.get("/changes", response_model=ChangeReport)
def changes_since_last_scan(session: Session = Depends(get_session)) -> ChangeReport:
    scans = _latest_scans(session, 2)
    if not scans:
        raise HTTPException(status_code=404, detail="no scans yet")

    latest = scans[0]
    if len(scans) == 1:
        return ChangeReport(
            latest_scan_id=latest.scan_id,
            previous_scan_id=None,
            new_assets=[],
            missing_assets=[],
            note="Only one scan so far, so there is nothing to compare against.",
        )

    previous = scans[1]
    now_seen = _assets_seen_in(session, latest.scan_id)
    before_seen = _assets_seen_in(session, previous.scan_id)

    return ChangeReport(
        latest_scan_id=latest.scan_id,
        previous_scan_id=previous.scan_id,
        new_assets=sorted(now_seen - before_seen),
        missing_assets=sorted(before_seen - now_seen),
        note=(
            "Missing means not seen as AI in the latest scan. It may be deleted, moved, "
            "cleared on review, or hidden by a coverage gap. Check /coverage/latest first."
        ),
    )

NeedsText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

NEEDS_REVIEW_APPROVALS = {"potential_shadow_ai", "governance_exception"}
OPEN_REVIEW_STATUSES = {ReviewStatus.PENDING_REVIEW.value, ReviewStatus.ESCALATED.value}
RISK_ORDER = {"high": 0, "medium": 1, "low": 2, "unassessed": 3}


class ReviewRequest(BaseModel):
    asset_key: str
    decision: Literal["approve", "escalate"]
    reviewer: NeedsText
    reason: NeedsText


class ReviewItem(BaseModel):
    review_id: str
    asset_key: str
    status: str
    reviewer: str | None
    reason: str | None
    created_at: datetime


class QueueItem(BaseModel):
    asset_key: str
    name: str
    ai_verdict: str
    approval_status: str
    risk_tier: str
    review_status: str
    last_reviewer: str | None
    last_reason: str | None
    reasoning: str


def _to_review_item(review: GovernanceReview) -> ReviewItem:
    return ReviewItem(
        review_id=review.review_id,
        asset_key=review.asset_key,
        status=review.status,
        reviewer=review.reviewer,
        reason=review.reason,
        created_at=review.created_at,
    )


def _latest_observations(session: Session) -> dict[str, AssetObservation]:
    """Newest observation per asset, from the latest scan only."""
    scans = _latest_scans(session, 1)
    if not scans:
        return {}
    in_latest_scan = (
        select(AssetObservation)
        .where(AssetObservation.scan_id == scans[0].scan_id)
        .order_by(AssetObservation.observed_at.desc())
    )
    latest: dict[str, AssetObservation] = {}
    for observation in session.scalars(in_latest_scan):
        latest.setdefault(observation.asset_key, observation)
    return latest


def _latest_reviews(session: Session) -> dict[str, GovernanceReview]:
    latest: dict[str, GovernanceReview] = {}
    newest_first = select(GovernanceReview).order_by(GovernanceReview.created_at.desc())
    for review in session.scalars(newest_first):
        latest.setdefault(review.asset_key, review)
    return latest


@app.get("/reviews/queue", response_model=list[QueueItem])
def review_queue(session: Session = Depends(get_session)) -> list[QueueItem]:
    observations = _latest_observations(session)
    reviews = _latest_reviews(session)
    names = {asset.asset_key: asset.name for asset in session.scalars(select(AIAsset))}

    queue: list[QueueItem] = []
    for asset_key, obs in observations.items():
        needs_a_person = obs.review_required or obs.approval_status in NEEDS_REVIEW_APPROVALS
        review = reviews.get(asset_key)
        status = review.status if review else ReviewStatus.PENDING_REVIEW.value
        if not needs_a_person or status not in OPEN_REVIEW_STATUSES:
            continue
        queue.append(
            QueueItem(
                asset_key=asset_key,
                name=names.get(asset_key, asset_key),
                ai_verdict=obs.ai_verdict,
                approval_status=obs.approval_status,
                risk_tier=obs.risk_tier,
                review_status=status,
                last_reviewer=review.reviewer if review else None,
                last_reason=review.reason if review else None,
                reasoning=obs.reasoning,
            )
        )
    return sorted(queue, key=lambda item: (RISK_ORDER.get(item.risk_tier, 9), item.asset_key))


@app.post("/reviews", response_model=ReviewItem, status_code=201)
def submit_review(
    request: ReviewRequest, session: Session = Depends(get_session)
) -> ReviewItem:
    if session.get(AIAsset, request.asset_key) is None:
        raise HTTPException(status_code=404, detail="asset not found")

    latest = _latest_observations(session).get(request.asset_key)
    status = ReviewStatus.APPROVED if request.decision == "approve" else ReviewStatus.ESCALATED
    review = GovernanceReview(
        asset_key=request.asset_key,
        observation_id=latest.observation_id if latest else None,
        status=status.value,
        reviewer=request.reviewer,
        reason=request.reason,
    )
    session.add(review)
    session.flush()  # fills in review_id and created_at
    return _to_review_item(review)


@app.get("/reviews/history", response_model=list[ReviewItem])
def review_history(asset_key: str, session: Session = Depends(get_session)) -> list[ReviewItem]:
    """Every decision ever made about one asset, newest first."""
    reviews = session.scalars(
        select(GovernanceReview)
        .where(GovernanceReview.asset_key == asset_key)
        .order_by(GovernanceReview.created_at.desc())
    ).all()
    return [_to_review_item(review) for review in reviews]