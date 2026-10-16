"""Pipeline tests: a full scan against moto AWS and a throwaway Postgres database."""

import io
import json
import zipfile

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import func, select
from ai_discovery.llm.providers import LLMProvider
from ai_discovery.llm.router import LLMRouter
from ai_discovery.llm.types import LLMRequest, LLMResponse, ModelSpec, ModelTier
from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.config import get_settings
from ai_discovery.db.base import Base
from ai_discovery.db.session import _get_session_factory, get_engine, session_scope
from ai_discovery.db.tables import AIAsset, AssetObservation, EvidenceRecord
from ai_discovery.governance.register import ApprovedRegister
from ai_discovery.pipeline.scan import run_scan

ACCOUNT_ID = "123456789012"
REGION = "ap-south-1"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-test-role"
FAKE_SECRET_VALUE = "sk-test-not-a-real-key"
TEST_DATABASE_URL = "postgresql+psycopg://discovery:discovery@localhost:5432/ai_discovery_test"
INVOICE_HELPER_KEY = f"aws:arn:aws:lambda:{REGION}:{ACCOUNT_ID}:function:invoice-helper"


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    _get_session_factory.cache_clear()


@pytest.fixture
def test_database(monkeypatch):
    """Point the app at the test database and start every test with empty tables."""
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    _clear_caches()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()
    _clear_caches()


@pytest.fixture
def aws_account(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    with mock_aws():
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }
        boto3.client("iam", region_name=REGION).create_role(
            RoleName="lambda-test-role", AssumeRolePolicyDocument=json.dumps(trust_policy)
        )
        yield


def _add_lambda(name: str, env: dict | None = None) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("handler.py", "def handler(event, context):\n    return 'ok'\n")
    params = {
        "FunctionName": name,
        "Runtime": "python3.11",
        "Role": ROLE_ARN,
        "Handler": "handler.handler",
        "Code": {"ZipFile": buffer.getvalue()},
    }
    if env:
        params["Environment"] = {"Variables": env}
    boto3.client("lambda", region_name=REGION).create_function(**params)


def _scan():
    scope = ScanScope(account_id=ACCOUNT_ID, regions=[REGION])
    return run_scan(AWSCollector(), scope, ApprovedRegister())


def test_scan_stores_ai_assets_and_skips_plain_resources(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    _add_lambda("report-builder")

    summary = _scan()

    assert summary.resources_seen == 2
    assert summary.assets_recorded == 1
    assert summary.verdict_counts == {"ai_suspected": 1, "not_ai_evidenced": 1}
    assert summary.scopes_with_gaps == 0

    with session_scope() as session:
        observation = session.scalars(select(AssetObservation)).one()
        assert observation.asset_key == INVOICE_HELPER_KEY
        assert observation.approval_status == "potential_shadow_ai"
        assert observation.owner_source == "unknown"
        assert observation.activity_status == "no_activity_observed"


def test_second_scan_adds_an_observation_and_keeps_first_seen(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})

    _scan()
    _scan()

    with session_scope() as session:
        asset = session.get(AIAsset, INVOICE_HELPER_KEY)
        observation_count = session.scalar(select(func.count()).select_from(AssetObservation))

        assert observation_count == 2
        assert asset.last_seen > asset.first_seen


def test_secret_value_never_reaches_the_database(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})

    _scan()

    with session_scope() as session:
        details = session.scalars(select(EvidenceRecord.detail)).all()
        reasons = session.scalars(select(AssetObservation.reasoning)).all()

    assert details == ["env var name OPENAI_API_KEY"]
    assert FAKE_SECRET_VALUE not in " ".join(details + reasons)

def test_lambda_invocations_make_the_asset_active(test_database, aws_account):
    from datetime import datetime, timezone

    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    boto3.client("cloudwatch", region_name=REGION).put_metric_data(
        Namespace="AWS/Lambda",
        MetricData=[
            {
                "MetricName": "Invocations",
                "Dimensions": [{"Name": "FunctionName", "Value": "invoice-helper"}],
                "Timestamp": datetime.now(timezone.utc),
                "Value": 4000,
                "Unit": "Count",
            }
        ],
    )

    _scan()

    with session_scope() as session:
        observation = session.scalars(select(AssetObservation)).one()

    assert observation.activity_status == "active_observed"
    assert observation.usage_count == 4000
    assert observation.usage_window_days == 30

SMALL = ModelSpec(
    tier=ModelTier.SMALL, model_name="fake-small",
    input_price_per_million=1.0, output_price_per_million=1.0,
)
LARGE = ModelSpec(
    tier=ModelTier.LARGE, model_name="fake-large",
    input_price_per_million=10.0, output_price_per_million=10.0,
)


class EchoInspectorProvider(LLMProvider):
    """Answers every request with a fixed verdict, citing the first evidence id it was sent."""

    def __init__(self, verdict: str) -> None:
        self._verdict = verdict
        self.requests: list[LLMRequest] = []

    def complete(self, request: LLMRequest, model_name: str) -> LLMResponse:
        self.requests.append(request)
        package = json.loads(request.user_prompt)
        answer = {
            "verdict": self._verdict,
            "confidence": 0.6,
            "reasoning": "Scripted answer for the test.",
            "evidence_ids": [package["evidence"][0]["id"]],
            "missing_evidence": ["runtime_invocations"],
        }
        return LLMResponse(
            text=json.dumps(answer), model_name=model_name,
            input_tokens=100, output_tokens=50, latency_ms=5,
        )


def _scan_with(router: LLMRouter):
    scope = ScanScope(account_id=ACCOUNT_ID, regions=[REGION])
    return run_scan(AWSCollector(), scope, ApprovedRegister(), router)


def _add_notebook(name: str) -> None:
    boto3.client("sagemaker", region_name=REGION).create_notebook_instance(
        NotebookInstanceName=name, InstanceType="ml.t3.medium", RoleArn=ROLE_ARN
    )


def test_only_ambiguous_findings_reach_the_llm(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})  # suspected
    _add_notebook("research-notebook")  # confirmed by the rules
    _add_lambda("report-builder")  # plain
    provider = EchoInspectorProvider("ai_suspected")
    router = LLMRouter(provider, SMALL, LARGE)

    _scan_with(router)

    assert len(provider.requests) == 1
    assert "invoice-helper" in provider.requests[0].user_prompt
    assert "research-notebook" not in provider.requests[0].user_prompt
    assert "report-builder" not in provider.requests[0].user_prompt


def test_llm_decision_is_stored_and_stays_in_review(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    router = LLMRouter(EchoInspectorProvider("ai_suspected"), SMALL, LARGE)

    _scan_with(router)

    with session_scope() as session:
        observation = session.scalars(select(AssetObservation)).one()
    assert observation.decided_by == "llm_inspector"
    assert observation.review_required


def test_llm_can_clear_a_finding_out_of_the_inventory(test_database, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    router = LLMRouter(EchoInspectorProvider("not_ai_evidenced"), SMALL, LARGE)

    summary = _scan_with(router)

    assert summary.assets_recorded == 0
    assert summary.verdict_counts == {"not_ai_evidenced": 1}