"""Cost endpoint tests: seed call rows directly, then read the report."""

import pytest
from fastapi.testclient import TestClient

from ai_discovery.api.main import app
from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import LLMCall, ScanRun
from datetime import datetime, timezone


def _call(scan_id, tier, outcome, cost, escalated_from=None):
    return LLMCall(
        scan_id=scan_id, task="inspect_resource", tier=tier, model_name=f"fake-{tier}",
        input_tokens=1000, output_tokens=500, cost_usd=cost, latency_ms=5,
        outcome=outcome, escalated_from=escalated_from, called_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def client(test_database):
    return TestClient(app)


def test_no_scans_gives_404(client):
    assert client.get("/llm/cost").status_code == 404


def test_scan_without_llm_calls_reports_llm_not_used(client):
    with session_scope() as session:
        session.add(ScanRun(scan_mode="mock"))

    body = client.get("/llm/cost").json()

    assert body["llm_used"] is False
    assert body["total_calls"] == 0
    assert body["total_cost_usd"] == 0


def test_report_counts_tiers_escalations_and_cost(client):
    with session_scope() as session:
        scan = ScanRun(scan_mode="mock")
        session.add(scan)
        session.flush()
        session.add_all([
            _call(scan.scan_id, "small", "ok", 0.001),
            _call(scan.scan_id, "small", "invalid_output", 0.001),
            _call(scan.scan_id, "large", "ok", 0.015, escalated_from="small"),
        ])

    body = client.get("/llm/cost").json()

    assert body["llm_used"] is True
    assert body["calls_by_tier"] == {"small": 2, "large": 1}
    assert body["escalated_calls"] == 1
    assert body["total_cost_usd"] == pytest.approx(0.017)
    assert body["cost_by_task"] == {"inspect_resource": pytest.approx(0.017)}