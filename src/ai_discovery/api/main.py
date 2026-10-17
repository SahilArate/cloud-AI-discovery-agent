"""HTTP API: health check and the current AI inventory."""

from collections.abc import Iterator
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AIAsset, AssetObservation, ScanRun, ScanScopeResult
from sqlalchemy.dialects.postgresql import distinct_on

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
def inventory(session: Session = Depends(get_session)) -> list[InventoryItem]:
    """Latest observation for every asset we have ever recorded."""
    rows = session.execute(
        select(AssetObservation, AIAsset)
        .join(AIAsset, AIAsset.asset_key == AssetObservation.asset_key)
        .ext(distinct_on(AssetObservation.asset_key))
        .order_by(AssetObservation.asset_key, AssetObservation.observed_at.desc())
    ).all()

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