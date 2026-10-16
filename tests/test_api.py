"""API tests: a real scan fills the test database, then the endpoints read it."""

import io
import json
import zipfile

import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from ai_discovery.api.main import app
from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.config import get_settings
from ai_discovery.db.base import Base
from ai_discovery.db.session import _get_session_factory, get_engine
from ai_discovery.governance.register import ApprovedRegister
from ai_discovery.pipeline.scan import run_scan

ACCOUNT_ID = "123456789012"
REGION = "ap-south-1"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-test-role"
FAKE_SECRET_VALUE = "sk-test-not-a-real-key"
TEST_DATABASE_URL = "postgresql+psycopg://discovery:discovery@localhost:5432/ai_discovery_test"


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    _get_session_factory.cache_clear()


@pytest.fixture
def test_database(monkeypatch):
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


def _scan() -> None:
    scope = ScanScope(account_id=ACCOUNT_ID, regions=[REGION])
    run_scan(AWSCollector(), scope, ApprovedRegister())


@pytest.fixture
def client(test_database):
    return TestClient(app)


def test_health_check_reaches_the_database(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_database_gives_empty_inventory(client):
    response = client.get("/inventory")

    assert response.status_code == 200
    assert response.json() == []


def test_inventory_lists_each_asset_once_after_several_scans(client, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    _scan()
    _scan()
    _scan()

    items = client.get("/inventory").json()

    assert len(items) == 1
    assert items[0]["name"] == "invoice-helper"
    assert items[0]["ai_verdict"] == "ai_suspected"
    assert items[0]["approval_status"] == "potential_shadow_ai"


def test_inventory_never_exposes_a_secret_value(client, aws_account):
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_SECRET_VALUE})
    _scan()

    response = client.get("/inventory")

    assert FAKE_SECRET_VALUE not in response.text