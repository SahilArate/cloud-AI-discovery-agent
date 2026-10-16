"""HTTP API: health check and the current AI inventory."""

from collections.abc import Iterator
from datetime import datetime

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AIAsset, AssetObservation

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
        .distinct(AssetObservation.asset_key)
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