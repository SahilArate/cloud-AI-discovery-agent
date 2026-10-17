"""Review queue tests: decisions are appended, never edited, and approved items leave the queue."""

import pytest
from fastapi.testclient import TestClient

from ai_discovery.api.main import app
from ai_discovery.collectors.base import ScanScope
from ai_discovery.collectors.gcp import GCPCollector
from ai_discovery.governance.register import ApprovedRegister
from ai_discovery.pipeline.scan import run_scan

PROJECT = "demo-project"
REGION = "asia-south1"
ENDPOINT_KEY = f"gcp:projects/{PROJECT}/locations/{REGION}/endpoints/churn"
SECRET_KEY = f"gcp:projects/{PROJECT}/secrets/OPENAI_API_KEY"


class _SeedGCPApi:
    def list_vertex_endpoints(self, project, region):
        return [{"name": f"projects/{project}/locations/{region}/endpoints/churn"}]

    def list_cloud_run_services(self, project, region):
        return []

    def list_compute_instances(self, project, region):
        return []

    def list_secrets(self, project):
        return [{"name": f"projects/{project}/secrets/OPENAI_API_KEY"}]


@pytest.fixture
def client(test_database):
    scope = ScanScope(account_id=PROJECT, regions=[REGION])
    run_scan(GCPCollector(_SeedGCPApi()), scope, ApprovedRegister())
    return TestClient(app)


def _decide(client, asset_key, decision, reviewer="priya", reason="checked with the owner"):
    return client.post(
        "/reviews",
        json={"asset_key": asset_key, "decision": decision, "reviewer": reviewer, "reason": reason},
    )


def test_queue_lists_unapproved_ai_with_high_risk_first(client):
    queue = client.get("/reviews/queue").json()

    assert [item["asset_key"] for item in queue] == [ENDPOINT_KEY, SECRET_KEY]
    assert queue[0]["risk_tier"] == "high"
    assert queue[0]["review_status"] == "pending_review"


def test_approving_removes_the_asset_from_the_queue(client):
    response = _decide(client, ENDPOINT_KEY, "approve")

    assert response.status_code == 201
    assert response.json()["status"] == "approved"
    queue_keys = [item["asset_key"] for item in client.get("/reviews/queue").json()]
    assert queue_keys == [SECRET_KEY]


def test_escalating_keeps_the_asset_in_the_queue(client):
    _decide(client, SECRET_KEY, "escalate", reason="key may belong to a contractor")

    item = next(i for i in client.get("/reviews/queue").json() if i["asset_key"] == SECRET_KEY)

    assert item["review_status"] == "escalated"
    assert item["last_reviewer"] == "priya"
    assert item["last_reason"] == "key may belong to a contractor"


def test_history_keeps_every_decision_newest_first(client):
    _decide(client, ENDPOINT_KEY, "escalate", reason="unclear owner")
    _decide(client, ENDPOINT_KEY, "approve", reason="owner confirmed")

    history = client.get("/reviews/history", params={"asset_key": ENDPOINT_KEY}).json()

    assert [entry["status"] for entry in history] == ["approved", "escalated"]


def test_reviewer_and_reason_are_required(client):
    assert _decide(client, ENDPOINT_KEY, "approve", reviewer="  ").status_code == 422
    assert _decide(client, ENDPOINT_KEY, "approve", reason="").status_code == 422
    assert client.get("/reviews/history", params={"asset_key": ENDPOINT_KEY}).json() == []


def test_review_of_an_unknown_asset_is_a_404(client):
    assert _decide(client, "gcp:does-not-exist", "approve").status_code == 404