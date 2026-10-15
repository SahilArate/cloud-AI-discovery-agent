"""Builds a messy fake AWS account in moto and runs a full scan against Postgres.

Usage: python scripts/demo_scan.py
Needs the database running and migrated (docker compose up -d, alembic upgrade head).
"""

import io
import json
import os
import zipfile

import boto3
from moto import mock_aws
from sqlalchemy import select

from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AssetObservation, ScanScopeResult
from ai_discovery.governance.register import ApprovedEntry, ApprovedRegister
from ai_discovery.models.enums import CloudProvider
from ai_discovery.pipeline.scan import run_scan

# Fake credentials, so nothing here can ever reach a real account.
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"

ACCOUNT_ID = "123456789012"
HOME_REGION = "ap-south-1"
OTHER_REGION = "us-east-1"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/demo-role"
FAKE_KEY_VALUE = "sk-demo-not-a-real-key"


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("handler.py", "def handler(event, context):\n    return 'ok'\n")
    return buffer.getvalue()


def _create_role() -> None:
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
    boto3.client("iam", region_name=HOME_REGION).create_role(
        RoleName="demo-role", AssumeRolePolicyDocument=json.dumps(trust_policy)
    )


def _add_lambda(name: str, env: dict | None = None, tags: dict | None = None) -> None:
    client = boto3.client("lambda", region_name=HOME_REGION)
    params = {
        "FunctionName": name,
        "Runtime": "python3.11",
        "Role": ROLE_ARN,
        "Handler": "handler.handler",
        "Code": {"ZipFile": _zip_bytes()},
        "Tags": tags or {},
    }
    if env:
        params["Environment"] = {"Variables": env}
    client.create_function(**params)


def _add_endpoint(name: str, tags: list[dict] | None = None) -> None:
    client = boto3.client("sagemaker", region_name=HOME_REGION)
    client.create_model(
        ModelName=f"{name}-model",
        PrimaryContainer={"Image": f"{ACCOUNT_ID}.dkr.ecr.{HOME_REGION}.amazonaws.com/demo:latest"},
        ExecutionRoleArn=ROLE_ARN,
    )
    client.create_endpoint_config(
        EndpointConfigName=f"{name}-config",
        ProductionVariants=[
            {
                "VariantName": "main",
                "ModelName": f"{name}-model",
                "InitialInstanceCount": 1,
                "InstanceType": "ml.m5.large",
            }
        ],
    )
    client.create_endpoint(
        EndpointName=name, EndpointConfigName=f"{name}-config", Tags=tags or []
    )


def _add_notebook(name: str, region: str) -> None:
    boto3.client("sagemaker", region_name=region).create_notebook_instance(
        NotebookInstanceName=name, InstanceType="ml.t3.medium", RoleArn=ROLE_ARN
    )


def _add_gpu_instance(name: str) -> None:
    ec2 = boto3.client("ec2", region_name=HOME_REGION)
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    ec2.run_instances(
        ImageId=image_id,
        InstanceType="g5.xlarge",
        MinCount=1,
        MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": name}]}],
    )


def build_messy_account() -> None:
    _create_role()

    # Approved and tagged
    _add_lambda(
        "approved-summariser",
        env={"ANTHROPIC_API_KEY": FAKE_KEY_VALUE},
        tags={"owner": "finance-team"},
    )
    _add_endpoint("churn-predictor", tags=[{"Key": "owner", "Value": "data-science"}])

    # Nobody registered these
    _add_lambda("invoice-helper", env={"OPENAI_API_KEY": FAKE_KEY_VALUE, "LOG_LEVEL": "info"})
    _add_endpoint("shadow-embeddings")
    _add_gpu_instance("gpu-worker")

    # Registered, but running outside its approved region
    _add_notebook("research-notebook", region=OTHER_REGION)

    # Ordinary resources
    _add_lambda("report-builder")
    _add_lambda("image-resizer")

    boto3.client("secretsmanager", region_name=HOME_REGION).create_secret(
        Name="OPENAI_API_KEY", SecretString=FAKE_KEY_VALUE
    )


def build_register() -> ApprovedRegister:
    arn = f"arn:aws:%s:%s:{ACCOUNT_ID}:%s"
    return ApprovedRegister(
        entries=[
            ApprovedEntry(
                register_id="AI-001",
                name="Finance summariser",
                provider=CloudProvider.AWS,
                account_id=ACCOUNT_ID,
                native_ids=[arn % ("lambda", HOME_REGION, "function:approved-summariser")],
                approved_regions=[HOME_REGION],
                owner="finance-team",
            ),
            ApprovedEntry(
                register_id="AI-002",
                name="Churn model",
                provider=CloudProvider.AWS,
                account_id=ACCOUNT_ID,
                native_ids=[arn % ("sagemaker", HOME_REGION, "endpoint/churn-predictor")],
                approved_regions=[HOME_REGION],
                owner="data-science",
            ),
            ApprovedEntry(
                register_id="AI-003",
                name="Research notebook",
                provider=CloudProvider.AWS,
                account_id=ACCOUNT_ID,
                native_ids=[arn % ("sagemaker", OTHER_REGION, "notebook-instance/research-notebook")],
                approved_regions=[HOME_REGION],
            ),
        ]
    )


def print_results(summary) -> None:
    print(f"\nScan {summary.scan_id}")
    print(f"  resources seen : {summary.resources_seen}")
    print(f"  assets stored  : {summary.assets_recorded}")
    print(f"  verdicts       : {summary.verdict_counts}")
    print(f"  scopes w/ gaps : {summary.scopes_with_gaps}")

    with session_scope() as session:
        rows = session.scalars(
            select(AssetObservation)
            .where(AssetObservation.scan_id == summary.scan_id)
            .order_by(AssetObservation.asset_key)
        ).all()

        print("\nAI inventory from this scan")
        print(f"  {'asset':<50} {'verdict':<14} {'approval':<22} {'risk':<8} owner")
        for row in rows:
            short_name = row.asset_key.split(":", 1)[1].split(":")[-1]
            owner = f"{row.owner} ({row.owner_source})" if row.owner else "unknown"
            print(
                f"  {short_name:<50} {row.ai_verdict:<14} "
                f"{row.approval_status:<22} {row.risk_tier:<8} {owner}"
            )

        gaps = session.scalars(
            select(ScanScopeResult).where(
                ScanScopeResult.scan_id == summary.scan_id,
                ScanScopeResult.status != "complete",
            )
        ).all()
        if gaps:
            print("\nCoverage gaps")
            for gap in gaps:
                print(f"  {gap.region}/{gap.service}: {gap.status} {gap.errors}")


def main() -> None:
    with mock_aws():
        build_messy_account()
        scope = ScanScope(account_id=ACCOUNT_ID, regions=[HOME_REGION, OTHER_REGION])
        summary = run_scan(AWSCollector(), scope, build_register())
    print_results(summary)


if __name__ == "__main__":
    main()