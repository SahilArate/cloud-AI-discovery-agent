"""Pipeline tests: a full scan against moto AWS and a throwaway Postgres database."""

import io
import json
import zipfile

import boto3
import pytest
from moto import mock_aws
from sqlalchemy import func, select

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
        assert observation.activity_status == "activity_unknown"


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