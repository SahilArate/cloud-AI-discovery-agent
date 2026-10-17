"""Harness tests: the scorer must give 100% on a correct scan and fail on a broken one."""

from pathlib import Path

import pytest

from ai_discovery.cli import _run_mock_scan
from ai_discovery.db.session import session_scope
from ai_discovery.evals.scoring import evaluate_scan
from ai_discovery.governance.register import ApprovedRegister, load_register

REGISTER_PATH = Path(__file__).resolve().parent.parent / "data" / "approved_register.yaml"
ALL_CLOUDS = ["aws", "gcp", "azure"]


@pytest.fixture(autouse=True)
def fake_aws_credentials(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-south-1")


def _scan_and_score(register: ApprovedRegister):
    summary = _run_mock_scan(ALL_CLOUDS, register, router=None)
    with session_scope() as session:
        return evaluate_scan(session, summary.scan_id)


def test_correct_scan_scores_perfectly(test_database):
    report = _scan_and_score(load_register(REGISTER_PATH))

    assert report.mismatches == []
    assert report.unlabelled_assets == []
    assert report.detection_precision == 1.0
    assert report.detection_recall == 1.0
    assert report.verdict_accuracy == 1.0
    assert report.approval_accuracy == 1.0
    assert report.shadow_precision == 1.0
    assert report.shadow_recall == 1.0
    assert report.scopes_complete_ratio == 1.0


def test_broken_detection_drops_recall_to_zero(test_database, monkeypatch):
    # A detector that finds nothing: every AI resource is missed.
    monkeypatch.setattr("ai_discovery.pipeline.scan.gather_evidence", lambda resource, catalog: [])

    report = _scan_and_score(load_register(REGISTER_PATH))

    assert report.detection_recall == 0.0
    assert report.detection_precision is None  # nothing was flagged, so precision is undefined
    assert report.mismatches != []


def test_empty_register_lowers_shadow_precision(test_database):
    report = _scan_and_score(ApprovedRegister())

    # Approved assets now look like shadow AI, so some flags are wrong.
    assert report.shadow_precision is not None
    assert report.shadow_precision < 1.0
    assert report.shadow_recall == 1.0