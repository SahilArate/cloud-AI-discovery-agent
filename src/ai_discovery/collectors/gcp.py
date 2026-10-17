"""GCP collector. Read-only, and it talks to GCP only through the GCPApi interface."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from ai_discovery.collectors.base import BaseCollector, CollectionResult, ScanScope
from ai_discovery.models.coverage import CollectionError, ScopeCoverage
from ai_discovery.models.enums import CloudProvider, CoverageStatus
from ai_discovery.models.resource import Resource

GLOBAL_REGION = "global"


class GCPApiError(Exception):
    """A failed GCP call. Carries a short code like PERMISSION_DENIED, never a payload."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class GCPApi(Protocol):
    """Each method returns a list of dicts shaped like the GCP REST response items."""

    def list_vertex_endpoints(self, project: str, region: str) -> list[dict]: ...

    def list_cloud_run_services(self, project: str, region: str) -> list[dict]: ...

    def list_compute_instances(self, project: str, region: str) -> list[dict]: ...

    def list_secrets(self, project: str) -> list[dict]: ...


def _last_segment(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None  # GCP sometimes sends nanoseconds, which fromisoformat rejects


def _status_for(discovered: int, errors: list[CollectionError]) -> CoverageStatus:
    if not errors:
        return CoverageStatus.COMPLETE
    if discovered == 0:
        return CoverageStatus.FAILED
    return CoverageStatus.PARTIAL


class GCPCollector(BaseCollector):
    provider = CloudProvider.GCP

    def __init__(self, api: GCPApi) -> None:
        self._api = api

    def collect(self, scope: ScanScope) -> CollectionResult:
        """For GCP, scope.account_id is the project id."""
        project = scope.account_id
        result = CollectionResult()

        for region in scope.regions:
            scopes = (
                ("aiplatform", "aiplatform:ListEndpoints",
                 lambda: self._api.list_vertex_endpoints(project, region),
                 lambda item: self._build_endpoint(item, project, region)),
                ("run", "run:ListServices",
                 lambda: self._api.list_cloud_run_services(project, region),
                 lambda item: self._build_cloud_run(item, project, region)),
                ("compute", "compute:ListInstances",
                 lambda: self._api.list_compute_instances(project, region),
                 lambda item: self._build_instance(item, project, region)),
            )
            for service, operation, fetch, build in scopes:
                resources, coverage = self._gather(project, region, service, operation, fetch, build)
                result.resources.extend(resources)
                result.coverage.append(coverage)

        resources, coverage = self._gather(
            project, GLOBAL_REGION, "secretmanager", "secretmanager:ListSecrets",
            lambda: self._api.list_secrets(project),
            lambda item: self._build_secret(item, project),
        )
        result.resources.extend(resources)
        result.coverage.append(coverage)
        return result

    def _gather(
        self,
        project: str,
        region: str,
        service: str,
        operation: str,
        fetch: Callable[[], list[dict]],
        build: Callable[[dict], Resource],
    ) -> tuple[list[Resource], ScopeCoverage]:
        resources: list[Resource] = []
        errors: list[CollectionError] = []

        try:
            resources = [build(item) for item in fetch()]
        except GCPApiError as error:
            errors.append(CollectionError(code=error.code, operation=operation))

        coverage = ScopeCoverage(
            provider=CloudProvider.GCP,
            account_id=project,
            region=region,
            service=service,
            status=_status_for(len(resources), errors),
            resources_discovered=len(resources),
            resources_inspected=len(resources),
            errors=errors,
        )
        return resources, coverage

    def _build_endpoint(self, item: dict, project: str, region: str) -> Resource:
        native_id = item["name"]
        return Resource(
            provider=CloudProvider.GCP,
            account_id=project,
            region=region,
            service="aiplatform",
            resource_type="endpoint",
            native_id=native_id,
            name=item.get("displayName") or _last_segment(native_id),
            tags=item.get("labels", {}),
            created_at=_parse_time(item.get("createTime")),
            config={"deployed_models": len(item.get("deployedModels", []))},
        )

    def _build_cloud_run(self, item: dict, project: str, region: str) -> Resource:
        native_id = item["name"]
        containers = item.get("template", {}).get("containers", [])

        # Env var values are never read. Only the names are kept.
        env_names = sorted(
            {entry["name"] for container in containers for entry in container.get("env", [])}
        )
        images = [container.get("image") for container in containers if container.get("image")]

        return Resource(
            provider=CloudProvider.GCP,
            account_id=project,
            region=region,
            service="run",
            resource_type="service",
            native_id=native_id,
            name=_last_segment(native_id),
            tags=item.get("labels", {}),
            created_at=_parse_time(item.get("createTime")),
            env_var_names=env_names,
            config={"images": images},
        )

    def _build_instance(self, item: dict, project: str, region: str) -> Resource:
        name = item["name"]
        zone = _last_segment(item.get("zone", f"{region}-?"))
        return Resource(
            provider=CloudProvider.GCP,
            account_id=project,
            region=region,
            service="compute",
            resource_type="instance",
            native_id=f"projects/{project}/zones/{zone}/instances/{name}",
            name=name,
            tags=item.get("labels", {}),
            created_at=_parse_time(item.get("creationTimestamp")),
            config={
                "instance_type": _last_segment(item.get("machineType", "")),
                "state": item.get("status"),
            },
        )

    def _build_secret(self, item: dict, project: str) -> Resource:
        native_id = item["name"]
        return Resource(
            provider=CloudProvider.GCP,
            account_id=project,
            region=GLOBAL_REGION,
            service="secretmanager",
            resource_type="secret",
            native_id=native_id,
            name=_last_segment(native_id),
            tags=item.get("labels", {}),
            created_at=_parse_time(item.get("createTime")),
        )