"""Runs one scan end to end: collect, detect, enrich, assess, save."""

from collections import Counter
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from ai_discovery.agents.inspector import inspect
from ai_discovery.llm.router import LLMRouter
from ai_discovery.catalog.loader import load_catalog
from ai_discovery.collectors.base import BaseCollector, ScanScope
from ai_discovery.config import get_settings
from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import (
    AIAsset,
    AssetObservation,
    EvidenceRecord,
    ScanRun,
    ScanScopeResult,
)
from ai_discovery.detection.classifier import classify
from ai_discovery.detection.rules import gather_evidence
from ai_discovery.enrichment.owner import resolve_owner
from ai_discovery.enrichment.usage import summarise_usage
from ai_discovery.governance.register import ApprovedRegister
from ai_discovery.governance.shadow import assess
from ai_discovery.models.enums import AIVerdict
from ai_discovery.models.resource import Resource


class ScanSummary(BaseModel):
    scan_id: str
    resources_seen: int
    assets_recorded: int
    verdict_counts: dict[str, int]
    scopes_with_gaps: int


def _upsert_asset(session: Session, resource: Resource, now: datetime) -> None:
    asset = session.get(AIAsset, resource.asset_key)
    if asset is None:
        session.add(
            AIAsset(
                asset_key=resource.asset_key,
                provider=resource.provider.value,
                account_id=resource.account_id,
                native_id=resource.native_id,
                name=resource.name,
                first_seen=now,
                last_seen=now,
            )
        )
    else:
        # first_seen stays as it was, so "new this week" keeps working.
        asset.last_seen = now
        asset.name = resource.name


def run_scan(
    collector: BaseCollector,
    scope: ScanScope,
    register: ApprovedRegister,
    router: LLMRouter | None = None,
) -> ScanSummary:
    catalog = load_catalog(collector.provider)
    verdict_counts: Counter[str] = Counter()
    assets_recorded = 0

    with session_scope() as session:
        scan = ScanRun(scan_mode=get_settings().scan_mode.value)
        session.add(scan)
        session.flush()  # fills in scan_id

        result = collector.collect(scope)
        now = datetime.now(timezone.utc)

        for resource in result.resources:
            evidence = gather_evidence(resource, catalog)
            finding = classify(resource, evidence)
                        # Only ambiguous findings go to the LLM. Confirmed and clean ones never do.
            if router is not None and finding.verdict in (
                AIVerdict.AI_SUSPECTED,
                AIVerdict.UNKNOWN,
            ):
                finding = inspect(resource, finding, router)
            verdict_counts[finding.verdict.value] += 1

            # Resources with no AI evidence are counted but not stored as assets.
            if finding.verdict == AIVerdict.NOT_AI_EVIDENCED:
                continue

            owner = resolve_owner(resource)
            usage = summarise_usage(collector.read_usage(resource))
            match = register.match(resource, owner=owner.owner)
            assessment = assess(finding, match, owner.source)

            _upsert_asset(session, resource, now)
            observation = AssetObservation(
                asset_key=resource.asset_key,
                scan_id=scan.scan_id,
                ai_verdict=finding.verdict.value,
                activity_status=usage.activity_status.value,
                reasoning=finding.reasoning,
                decided_by=finding.decided_by,
                review_required=finding.review_required,
                missing_evidence=finding.missing_evidence,
                owner=owner.owner,
                owner_source=owner.source.value,
                usage_count=usage.usage_count,
                usage_window_days=usage.usage_window_days,
                region=resource.region,
                hosting_type=resource.service,
                approval_status=assessment.approval_status.value,
                risk_tier=assessment.risk_tier.value,
                observed_at=now,
            )
            for item in finding.evidence:
                observation.evidence.append(
                    EvidenceRecord(
                        evidence_id=item.evidence_id,
                        evidence_type=item.evidence_type.value,
                        strength=item.strength.value,
                        source=item.source,
                        detail=item.detail,
                        observed_at=item.observed_at,
                    )
                )
            session.add(observation)
            assets_recorded += 1

        for coverage in result.coverage:
            session.add(
                ScanScopeResult(
                    scan_id=scan.scan_id,
                    provider=coverage.provider.value,
                    account_id=coverage.account_id,
                    region=coverage.region,
                    service=coverage.service,
                    status=coverage.status.value,
                    resources_discovered=coverage.resources_discovered,
                    resources_inspected=coverage.resources_inspected,
                    errors=[error.model_dump() for error in coverage.errors],
                )
            )

        gaps = sum(1 for coverage in result.coverage if coverage.is_gap)
        scan.resources_seen = len(result.resources)
        scan.finished_at = datetime.now(timezone.utc)
        scan.status = "partial" if gaps else "complete"

        return ScanSummary(
            scan_id=scan.scan_id,
            resources_seen=len(result.resources),
            assets_recorded=assets_recorded,
            verdict_counts=dict(verdict_counts),
            scopes_with_gaps=gaps,
        )