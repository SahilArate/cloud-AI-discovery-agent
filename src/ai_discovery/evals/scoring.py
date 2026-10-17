"""Scores one stored scan against the hand-labelled ground truth."""

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AssetObservation, ScanRun, ScanScopeResult
from ai_discovery.evals.ground_truth import (
    EXPECTED_ASSETS,
    EXPECTED_BY_PREFIX,
    EXPECTED_NOT_AI,
)
from ai_discovery.models.enums import AIVerdict, ApprovalStatus

AI_VERDICTS = {AIVerdict.AI_CONFIRMED.value, AIVerdict.AI_SUSPECTED.value}
SHADOW = ApprovalStatus.POTENTIAL_SHADOW_AI.value

# What a resource we did not store looks like: not AI, nothing to approve.
NOT_STORED = (AIVerdict.NOT_AI_EVIDENCED.value, ApprovalStatus.NOT_ASSESSED.value)


class Mismatch(BaseModel):
    asset_key: str
    expected: tuple[str, str]  # (verdict, approval)
    actual: tuple[str, str]


class EvalReport(BaseModel):
    scan_id: str
    labelled_resources: int
    detection_precision: float | None
    detection_recall: float | None
    verdict_accuracy: float | None
    approval_accuracy: float | None
    shadow_precision: float | None
    shadow_recall: float | None
    scopes_complete_ratio: float | None
    resources_inspected_ratio: float | None
    mismatches: list[Mismatch] = Field(default_factory=list)
    unlabelled_assets: list[str] = Field(default_factory=list)


def _ratio(numerator: int, denominator: int) -> float | None:
    """None means 'nothing to measure', which is different from a score of zero."""
    return numerator / denominator if denominator else None


def _expected_labels(actual_keys: set[str]) -> dict[str, tuple[str, str]]:
    expected: dict[str, tuple[str, str]] = {}

    for item in EXPECTED_ASSETS:
        expected[item.asset_key] = (item.verdict.value, item.approval.value)
    for key in EXPECTED_NOT_AI:
        expected[key] = NOT_STORED
    for prefix, verdict, approval in EXPECTED_BY_PREFIX:
        matches = [key for key in actual_keys if key.startswith(prefix)]
        # No match leaves the prefix itself as the key, which shows up as a missed asset.
        for key in matches or [prefix]:
            expected[key] = (verdict.value, approval.value)
    return expected


def evaluate_scan(session: Session, scan_id: str) -> EvalReport:
    observations = session.scalars(
        select(AssetObservation).where(AssetObservation.scan_id == scan_id)
    ).all()
    actual = {obs.asset_key: (obs.ai_verdict, obs.approval_status) for obs in observations}
    expected = _expected_labels(set(actual))
    unlabelled = sorted(key for key in actual if key not in expected)

    detect_tp = detect_fp = detect_fn = 0
    shadow_tp = shadow_fp = shadow_fn = 0
    verdict_hits = approval_hits = 0
    mismatches: list[Mismatch] = []

    for key, (want_verdict, want_approval) in expected.items():
        got_verdict, got_approval = actual.get(key, NOT_STORED)

        want_ai, got_ai = want_verdict in AI_VERDICTS, got_verdict in AI_VERDICTS
        detect_tp += want_ai and got_ai
        detect_fp += got_ai and not want_ai
        detect_fn += want_ai and not got_ai

        want_shadow, got_shadow = want_approval == SHADOW, got_approval == SHADOW
        shadow_tp += want_shadow and got_shadow
        shadow_fp += got_shadow and not want_shadow
        shadow_fn += want_shadow and not got_shadow

        verdict_hits += got_verdict == want_verdict
        approval_hits += got_approval == want_approval
        if (got_verdict, got_approval) != (want_verdict, want_approval):
            mismatches.append(
                Mismatch(
                    asset_key=key,
                    expected=(want_verdict, want_approval),
                    actual=(got_verdict, got_approval),
                )
            )

    # Anything stored without a label is a false positive if we called it AI or shadow.
    for key in unlabelled:
        verdict, approval = actual[key]
        detect_fp += verdict in AI_VERDICTS
        shadow_fp += approval == SHADOW

    scopes = session.scalars(
        select(ScanScopeResult).where(ScanScopeResult.scan_id == scan_id)
    ).all()
    complete = sum(1 for scope in scopes if scope.status == "complete")
    discovered = sum(scope.resources_discovered for scope in scopes)
    inspected = sum(scope.resources_inspected for scope in scopes)

    total = len(expected)
    return EvalReport(
        scan_id=scan_id,
        labelled_resources=total,
        detection_precision=_ratio(detect_tp, detect_tp + detect_fp),
        detection_recall=_ratio(detect_tp, detect_tp + detect_fn),
        verdict_accuracy=_ratio(verdict_hits, total),
        approval_accuracy=_ratio(approval_hits, total),
        shadow_precision=_ratio(shadow_tp, shadow_tp + shadow_fp),
        shadow_recall=_ratio(shadow_tp, shadow_tp + shadow_fn),
        scopes_complete_ratio=_ratio(complete, len(scopes)),
        resources_inspected_ratio=_ratio(inspected, discovered),
        mismatches=mismatches,
        unlabelled_assets=unlabelled,
    )


def _percent(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0%}"


def print_report(report: EvalReport) -> None:
    print(f"Evaluation of {report.scan_id} ({report.labelled_resources} labelled resources)")
    print(f"  detection precision : {_percent(report.detection_precision)}")
    print(f"  detection recall    : {_percent(report.detection_recall)}")
    print(f"  verdict accuracy    : {_percent(report.verdict_accuracy)}")
    print(f"  approval accuracy   : {_percent(report.approval_accuracy)}")
    print(f"  shadow AI precision : {_percent(report.shadow_precision)}")
    print(f"  shadow AI recall    : {_percent(report.shadow_recall)}")
    print(f"  scopes complete     : {_percent(report.scopes_complete_ratio)}")
    print(f"  resources inspected : {_percent(report.resources_inspected_ratio)}")
    for item in report.mismatches:
        print(f"  MISMATCH {item.asset_key}: expected {item.expected}, got {item.actual}")
    for key in report.unlabelled_assets:
        print(f"  UNLABELLED {key}")


if __name__ == "__main__":
    with session_scope() as session:
        latest = session.scalars(
            select(ScanRun).order_by(ScanRun.started_at.desc()).limit(1)
        ).first()
        if latest is None:
            raise SystemExit("no scans yet. Run a scan first.")
        print_report(evaluate_scan(session, latest.scan_id))