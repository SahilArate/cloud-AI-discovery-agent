"""Detection tests: resource in, evidence and verdict out. No cloud, no moto needed."""

import pytest

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.detection.classifier import classify
from ai_discovery.detection.rules import gather_evidence
from ai_discovery.models.enums import AIVerdict, CloudProvider, EvidenceType
from ai_discovery.models.resource import Resource

ACCOUNT_ID = "123456789012"
REGION = "ap-south-1"


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CloudProvider.AWS)


def _make_resource(service: str, resource_type: str, name: str, **extra) -> Resource:
    return Resource(
        provider=CloudProvider.AWS,
        account_id=ACCOUNT_ID,
        region=REGION,
        service=service,
        resource_type=resource_type,
        native_id=f"arn:aws:{service}:{REGION}:{ACCOUNT_ID}:{resource_type}/{name}",
        name=name,
        **extra,
    )


def _judge(resource: Resource, catalog):
    return classify(resource, gather_evidence(resource, catalog))


def test_sagemaker_endpoint_is_confirmed_ai(catalog):
    finding = _judge(_make_resource("sagemaker", "endpoint", "churn-predictor"), catalog)

    assert finding.verdict == AIVerdict.AI_CONFIRMED
    assert not finding.review_required


def test_lambda_with_only_a_key_name_is_suspected_not_confirmed(catalog):
    resource = _make_resource(
        "lambda", "function", "invoice-helper", env_var_names=["OPENAI_API_KEY"]
    )

    finding = _judge(resource, catalog)

    assert finding.verdict == AIVerdict.AI_SUSPECTED
    assert finding.review_required
    assert "runtime_invocations" in finding.missing_evidence


def test_gpu_instance_alone_is_unknown(catalog):
    resource = _make_resource(
        "ec2", "instance", "simulation-box", config={"instance_type": "g5.xlarge"}
    )

    finding = _judge(resource, catalog)

    assert finding.verdict == AIVerdict.UNKNOWN
    assert finding.review_required


def test_sagemaker_style_gpu_type_is_recognised(catalog):
    resource = _make_resource(
        "sagemaker", "notebook_instance", "scratch", config={"instance_type": "ml.g5.xlarge"}
    )

    evidence = gather_evidence(resource, catalog)

    assert EvidenceType.GPU_INSTANCE_TYPE in {item.evidence_type for item in evidence}


def test_name_hint_matches_whole_words_only(catalog):
    hinted = gather_evidence(_make_resource("lambda", "function", "invoice-rag-helper"), catalog)
    not_hinted = gather_evidence(_make_resource("s3", "bucket", "storage-fragments"), catalog)

    assert [item.evidence_type for item in hinted] == [EvidenceType.NAME_HINT]
    assert not_hinted == []


def test_plain_resource_is_not_ai_evidenced(catalog):
    finding = _judge(_make_resource("lambda", "function", "report-builder"), catalog)

    assert finding.verdict == AIVerdict.NOT_AI_EVIDENCED
    assert finding.evidence == []
    assert not finding.review_required


def test_secret_named_like_an_ai_key_is_a_lead(catalog):
    resource = _make_resource("secretsmanager", "secret", "OPENAI_API_KEY")

    finding = _judge(resource, catalog)

    assert finding.verdict == AIVerdict.AI_SUSPECTED


def test_evidence_never_contains_a_secret_value(catalog):
    resource = _make_resource(
        "lambda", "function", "invoice-helper", env_var_names=["OPENAI_API_KEY"]
    )

    evidence = gather_evidence(resource, catalog)

    assert evidence[0].detail == "env var name OPENAI_API_KEY"


LAYER_BASE = f"arn:aws:lambda:{REGION}:{ACCOUNT_ID}:layer"


def test_ai_package_layer_is_supporting_evidence(catalog):
    resource = _make_resource(
        "lambda", "function", "report-builder",
        config={"layers": [f"{LAYER_BASE}:openai-python:3"]},
    )

    evidence = gather_evidence(resource, catalog)

    assert [item.evidence_type for item in evidence] == [EvidenceType.AI_DEPENDENCY]
    assert evidence[0].detail == "layer openai-python matches AI package openai"
    assert _judge(resource, catalog).verdict == AIVerdict.AI_SUSPECTED


def test_unrelated_layer_is_not_evidence(catalog):
    resource = _make_resource(
        "lambda", "function", "report-builder",
        config={"layers": [f"{LAYER_BASE}:shared-utils:1"]},
    )

    assert gather_evidence(resource, catalog) == []


def test_layer_match_respects_package_boundaries(catalog):
    # "torch" sits inside "pytorch" and "torchlight", but is not a standalone word there.
    resource = _make_resource(
        "lambda", "function", "report-builder",
        config={"layers": [f"{LAYER_BASE}:torchlight-theme:1"]},
    )

    assert gather_evidence(resource, catalog) == []