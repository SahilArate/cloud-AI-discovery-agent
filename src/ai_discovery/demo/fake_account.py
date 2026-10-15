"""A messy fake AWS account for demos. Only ever used inside moto's mock_aws()."""

import io
import json
import os
import zipfile

import boto3

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
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
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