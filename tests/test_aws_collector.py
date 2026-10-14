"""AWS collector tests, run against moto so no real account is needed."""

import io
import zipfile
import json

import boto3
import pytest
from moto import mock_aws

from botocore.exceptions import ClientError
from ai_discovery.collectors.aws import AWSCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.models.enums import CoverageStatus

ACCOUNT_ID = "123456789012"  # moto's default account id
REGION = "ap-south-1"
FAKE_SECRET_VALUE = "sk-test-not-a-real-key"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/lambda-test-role"

def _create_lambda_role() -> None:
    """Moto checks the role exists and that Lambda is allowed to assume it."""
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
        RoleName="lambda-test-role",
        AssumeRolePolicyDocument=json.dumps(trust_policy),
    )

@pytest.fixture
def aws_credentials(monkeypatch):
    """Fake credentials so a test can never touch a real account by accident."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def lambda_client(aws_credentials):
    with mock_aws():
        _create_lambda_role()
        yield boto3.client("lambda", region_name=REGION)


def _dummy_code() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("handler.py", "def handler(event, context):\n    return 'ok'\n")
    return buffer.getvalue()


def _create_function(client, name: str, env: dict | None = None, tags: dict | None = None):
    kwargs = {
        "FunctionName": name,
        "Runtime": "python3.11",
        "Role": ROLE_ARN,
        "Handler": "handler.handler",
        "Code": {"ZipFile": _dummy_code()},
        "Tags": tags or {},
    }
    if env:
        kwargs["Environment"] = {"Variables": env}
    client.create_function(**kwargs)


def _collect():
    scope = ScanScope(account_id=ACCOUNT_ID, regions=[REGION])
    return AWSCollector().collect(scope)


def test_finds_lambda_functions(lambda_client):
    _create_function(lambda_client, "invoice-helper")
    _create_function(lambda_client, "report-builder")

    result = _collect()

    names = sorted(resource.name for resource in result.resources)
    assert names == ["invoice-helper", "report-builder"]


def test_keeps_env_var_names_but_never_values(lambda_client):
    _create_function(
        lambda_client,
        "invoice-helper",
        env={"OPENAI_API_KEY": FAKE_SECRET_VALUE, "LOG_LEVEL": "info"},
    )

    result = _collect()
    resource = result.resources[0]

    assert resource.env_var_names == ["LOG_LEVEL", "OPENAI_API_KEY"]
    # Check the whole serialised resource, not just one field.
    assert FAKE_SECRET_VALUE not in resource.model_dump_json()


def test_collects_tags(lambda_client):
    _create_function(lambda_client, "invoice-helper", tags={"owner": "finance-team"})

    result = _collect()

    assert result.resources[0].tags == {"owner": "finance-team"}


def test_function_without_env_vars_has_empty_name_list(lambda_client):
    _create_function(lambda_client, "report-builder")

    result = _collect()

    assert result.resources[0].env_var_names == []


def test_reports_complete_coverage_when_nothing_fails(lambda_client):
    _create_function(lambda_client, "invoice-helper")

    result = _collect()

    coverage = result.coverage[0]
    assert coverage.service == "lambda"
    assert coverage.status == CoverageStatus.COMPLETE
    assert coverage.resources_discovered == 1
    assert coverage.resources_inspected == 1
    assert coverage.errors == []

@pytest.fixture
def sagemaker_client(aws_credentials):
    with mock_aws():
        yield boto3.client("sagemaker", region_name=REGION)


def _create_notebook(client, name: str, tags: list[dict] | None = None):
    client.create_notebook_instance(
        NotebookInstanceName=name,
        InstanceType="ml.t3.medium",
        RoleArn=ROLE_ARN,
        Tags=tags or [],
    )


def _create_endpoint(client, name: str, tags: list[dict] | None = None):
    client.create_model(
        ModelName=f"{name}-model",
        PrimaryContainer={"Image": "123456789012.dkr.ecr.ap-south-1.amazonaws.com/demo:latest"},
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
        EndpointName=name,
        EndpointConfigName=f"{name}-config",
        Tags=tags or [],
    )


def _coverage_for(result, service: str):
    return next(item for item in result.coverage if item.service == service)


def test_finds_sagemaker_endpoint_and_notebook(sagemaker_client):
    _create_notebook(sagemaker_client, "research-notebook")
    _create_endpoint(sagemaker_client, "churn-predictor")

    result = _collect()

    found = {
        (resource.resource_type, resource.name)
        for resource in result.resources
        if resource.service == "sagemaker"
    }
    assert found == {
        ("notebook_instance", "research-notebook"),
        ("endpoint", "churn-predictor"),
    }


def test_sagemaker_tags_become_a_plain_dict(sagemaker_client):
    _create_endpoint(
        sagemaker_client,
        "churn-predictor",
        tags=[{"Key": "owner", "Value": "data-science"}],
    )

    result = _collect()

    endpoint = next(r for r in result.resources if r.resource_type == "endpoint")
    assert endpoint.tags == {"owner": "data-science"}


def test_denied_list_endpoints_is_a_partial_gap_not_a_crash(sagemaker_client):
    _create_notebook(sagemaker_client, "research-notebook")

    def deny_list_endpoints(**kwargs):
        raise ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "not allowed"}},
            "ListEndpoints",
        )

    session = boto3.Session()
    session.events.register("before-call.sagemaker.ListEndpoints", deny_list_endpoints)
    scope = ScanScope(account_id=ACCOUNT_ID, regions=[REGION])

    result = AWSCollector(session=session).collect(scope)

    # The notebook is still found even though endpoints were blocked.
    names = [r.name for r in result.resources if r.service == "sagemaker"]
    assert names == ["research-notebook"]

    coverage = _coverage_for(result, "sagemaker")
    assert coverage.status == CoverageStatus.PARTIAL
    assert coverage.is_gap
    assert coverage.errors[0].code == "AccessDeniedException"
    assert coverage.errors[0].operation == "sagemaker:ListEndpoints"

@pytest.fixture
def aws_account(aws_credentials):
    """One moto account shared by EC2 and Secrets Manager tests."""
    with mock_aws():
        yield


def _launch_instance(instance_type: str, tags: list[dict] | None = None) -> str:
    ec2 = boto3.client("ec2", region_name=REGION)
    # Moto ships a default image, so we look one up instead of hardcoding an id.
    image_id = ec2.describe_images()["Images"][0]["ImageId"]
    params = {
        "ImageId": image_id,
        "InstanceType": instance_type,
        "MinCount": 1,
        "MaxCount": 1,
    }
    if tags:
        params["TagSpecifications"] = [{"ResourceType": "instance", "Tags": tags}]
    return ec2.run_instances(**params)["Instances"][0]["InstanceId"]


def test_finds_ec2_instance_with_type_and_name_tag(aws_account):
    _launch_instance("g5.xlarge", tags=[{"Key": "Name", "Value": "gpu-worker"}])

    result = _collect()

    instance = next(r for r in result.resources if r.service == "ec2")
    assert instance.name == "gpu-worker"
    assert instance.config["instance_type"] == "g5.xlarge"
    assert instance.native_id.startswith(f"arn:aws:ec2:{REGION}:{ACCOUNT_ID}:instance/i-")


def test_ec2_instance_without_name_tag_uses_instance_id(aws_account):
    instance_id = _launch_instance("t3.micro")

    result = _collect()

    instance = next(r for r in result.resources if r.service == "ec2")
    assert instance.name == instance_id


def test_secrets_are_collected_by_name_only(aws_account):
    secrets = boto3.client("secretsmanager", region_name=REGION)
    secrets.create_secret(Name="OPENAI_API_KEY", SecretString=FAKE_SECRET_VALUE)

    result = _collect()

    secret = next(r for r in result.resources)

def test_full_scan_reports_coverage_for_all_four_services(aws_account):
    result = _collect()

    services = sorted(item.service for item in result.coverage)
    assert services == ["ec2", "lambda", "sagemaker", "secretsmanager"]
    assert all(item.status == CoverageStatus.COMPLETE for item in result.coverage)