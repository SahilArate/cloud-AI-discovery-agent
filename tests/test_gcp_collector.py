"""GCP collector tests: a fake GCPApi returns realistic GCP-shaped responses."""

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.collectors.base import ScanScope
from ai_discovery.collectors.gcp import GCPApiError, GCPCollector
from ai_discovery.detection.classifier import classify
from ai_discovery.detection.rules import gather_evidence
from ai_discovery.models.enums import AIVerdict, CloudProvider, CoverageStatus

PROJECT = "demo-project"
REGION = "asia-south1"
FAKE_SECRET_VALUE = "sk-test-not-a-real-key"


class FakeGCPApi:
    def __init__(self, endpoints=None, services=None, instances=None, secrets=None, deny=()):
        self._endpoints = endpoints or []
        self._services = services or []
        self._instances = instances or []
        self._secrets = secrets or []
        self._deny = set(deny)

    def _check(self, operation: str) -> None:
        if operation in self._deny:
            raise GCPApiError("PERMISSION_DENIED")

    def list_vertex_endpoints(self, project, region):
        self._check("vertex")
        return self._endpoints

    def list_cloud_run_services(self, project, region):
        self._check("run")
        return self._services

    def list_compute_instances(self, project, region):
        self._check("compute")
        return self._instances

    def list_secrets(self, project):
        self._check("secrets")
        return self._secrets


def _collect(api: FakeGCPApi):
    scope = ScanScope(account_id=PROJECT, regions=[REGION])
    return GCPCollector(api).collect(scope)


def _vertex_endpoint(name="churn", labels=None):
    return {
        "name": f"projects/{PROJECT}/locations/{REGION}/endpoints/{name}",
        "displayName": name,
        "labels": labels or {},
        "createTime": "2026-09-01T10:00:00+00:00",
        "deployedModels": [{"id": "1"}],
    }


def _cloud_run_service(name="invoice-helper", env=None, labels=None):
    return {
        "name": f"projects/{PROJECT}/locations/{REGION}/services/{name}",
        "labels": labels or {},
        "template": {
            "containers": [
                {
                    "image": "gcr.io/demo/app:latest",
                    "env": [{"name": key, "value": value} for key, value in (env or {}).items()],
                }
            ]
        },
    }


def _instance(name="gpu-worker", machine_type="a2-highgpu-1g", labels=None):
    return {
        "name": name,
        "zone": f"https://www.googleapis.com/compute/v1/projects/{PROJECT}/zones/{REGION}-a",
        "machineType": f".../zones/{REGION}-a/machineTypes/{machine_type}",
        "status": "RUNNING",
        "labels": labels or {},
    }


def test_finds_vertex_endpoint_and_maps_labels_to_tags():
    api = FakeGCPApi(endpoints=[_vertex_endpoint(labels={"owner": "data-science"})])

    result = _collect(api)

    endpoint = next(r for r in result.resources if r.service == "aiplatform")
    assert endpoint.name == "churn"
    assert endpoint.tags == {"owner": "data-science"}
    assert endpoint.provider == CloudProvider.GCP


def test_cloud_run_keeps_env_names_but_never_values():
    api = FakeGCPApi(
        services=[_cloud_run_service(env={"OPENAI_API_KEY": FAKE_SECRET_VALUE, "LOG_LEVEL": "info"})]
    )

    result = _collect(api)

    service = next(r for r in result.resources if r.service == "run")
    assert service.env_var_names == ["LOG_LEVEL", "OPENAI_API_KEY"]
    assert FAKE_SECRET_VALUE not in result.model_dump_json()


def test_compute_instance_records_machine_type_and_zone_in_the_id():
    api = FakeGCPApi(instances=[_instance()])

    result = _collect(api)

    instance = next(r for r in result.resources if r.service == "compute")
    assert instance.config["instance_type"] == "a2-highgpu-1g"
    assert instance.native_id == f"projects/{PROJECT}/zones/{REGION}-a/instances/gpu-worker"


def test_secrets_are_collected_once_under_global():
    api = FakeGCPApi(secrets=[{"name": f"projects/{PROJECT}/secrets/OPENAI_API_KEY"}])

    result = _collect(api)

    secret = next(r for r in result.resources if r.service == "secretmanager")
    assert secret.name == "OPENAI_API_KEY"
    assert secret.region == "global"


def test_clean_scan_reports_four_complete_scopes():
    result = _collect(FakeGCPApi())

    services = sorted(item.service for item in result.coverage)
    assert services == ["aiplatform", "compute", "run", "secretmanager"]
    assert all(item.status == CoverageStatus.COMPLETE for item in result.coverage)


def test_permission_denied_is_a_gap_and_other_services_still_work():
    api = FakeGCPApi(endpoints=[_vertex_endpoint()], deny=("run",))

    result = _collect(api)

    run_scope = next(item for item in result.coverage if item.service == "run")
    assert run_scope.status == CoverageStatus.FAILED
    assert run_scope.errors[0].code == "PERMISSION_DENIED"
    assert run_scope.errors[0].operation == "run:ListServices"
    assert any(r.service == "aiplatform" for r in result.resources)


def test_vertex_endpoint_is_confirmed_ai_by_the_shared_rules():
    result = _collect(FakeGCPApi(endpoints=[_vertex_endpoint()]))
    catalog = load_catalog(CloudProvider.GCP)
    resource = result.resources[0]

    finding = classify(resource, gather_evidence(resource, catalog))

    assert finding.verdict == AIVerdict.AI_CONFIRMED


def test_gpu_machine_type_and_api_key_name_are_recognised():
    api = FakeGCPApi(
        services=[_cloud_run_service(env={"GEMINI_API_KEY": FAKE_SECRET_VALUE})],
        instances=[_instance()],
    )
    result = _collect(api)
    catalog = load_catalog(CloudProvider.GCP)

    verdicts = {
        r.service: classify(r, gather_evidence(r, catalog)).verdict for r in result.resources
    }

    assert verdicts["run"] == AIVerdict.AI_SUSPECTED
    assert verdicts["compute"] == AIVerdict.UNKNOWN

def test_gcp_secret_named_like_an_ai_key_is_a_lead():
    api = FakeGCPApi(secrets=[{"name": f"projects/{PROJECT}/secrets/OPENAI_API_KEY"}])
    result = _collect(api)
    catalog = load_catalog(CloudProvider.GCP)
    secret = result.resources[0]

    finding = classify(secret, gather_evidence(secret, catalog))

    assert finding.verdict == AIVerdict.AI_SUSPECTED