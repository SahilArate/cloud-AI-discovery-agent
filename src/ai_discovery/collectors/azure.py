"""Azure collector. Read-only, and it talks to Azure only through the AzureApi interface."""

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from ai_discovery.collectors.base import (
    BaseCollector,
    CollectionResult,
    ScanScope,
    coverage_status_for,
)
from ai_discovery.models.coverage import CollectionError, ScopeCoverage
from ai_discovery.models.enums import CloudProvider
from ai_discovery.models.resource import Resource


class AzureApiError(Exception):
    """A failed Azure call. Carries a short code like AuthorizationFailed, never a payload."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class AzureApi(Protocol):
    """Each method returns a list of dicts shaped like ARM resource objects."""

    def list_cognitive_accounts(self, subscription: str, region: str) -> list[dict]: ...

    def list_ml_workspaces(self, subscription: str, region: str) -> list[dict]: ...

    def list_search_services(self, subscription: str, region: str) -> list[dict]: ...

    def list_web_apps(self, subscription: str, region: str) -> list[dict]: ...

    def list_virtual_machines(self, subscription: str, region: str) -> list[dict]: ...

    def list_key_vault_secrets(self, subscription: str, region: str) -> list[dict]: ...


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None  # Azure sometimes sends 7 fractional digits, which fromisoformat rejects


class AzureCollector(BaseCollector):
    provider = CloudProvider.AZURE

    def __init__(self, api: AzureApi) -> None:
        self._api = api

    def collect(self, scope: ScanScope) -> CollectionResult:
        """For Azure, scope.account_id is the subscription id."""
        subscription = scope.account_id
        result = CollectionResult()

        for region in scope.regions:
            listings = (
                ("cognitiveservices", "cognitiveservices:ListAccounts",
                 self._api.list_cognitive_accounts, self._build_cognitive_account),
                ("machinelearningservices", "machinelearningservices:ListWorkspaces",
                 self._api.list_ml_workspaces, self._build_ml_workspace),
                ("search", "search:ListSearchServices",
                 self._api.list_search_services, self._build_search_service),
                ("web", "web:ListSites",
                 self._api.list_web_apps, self._build_web_app),
                ("compute", "compute:ListVirtualMachines",
                 self._api.list_virtual_machines, self._build_virtual_machine),
                ("keyvault", "keyvault:ListSecrets",
                 self._api.list_key_vault_secrets, self._build_secret),
            )
            for service, operation, fetch, build in listings:
                resources, coverage = self._gather(
                    subscription, region, service, operation, fetch, build
                )
                result.resources.extend(resources)
                result.coverage.append(coverage)

        return result

    def _gather(
        self,
        subscription: str,
        region: str,
        service: str,
        operation: str,
        fetch: Callable[[str, str], list[dict]],
        build: Callable[[dict, str, str], Resource],
    ) -> tuple[list[Resource], ScopeCoverage]:
        resources: list[Resource] = []
        errors: list[CollectionError] = []

        try:
            resources = [build(item, subscription, region) for item in fetch(subscription, region)]
        except AzureApiError as error:
            errors.append(CollectionError(code=error.code, operation=operation))

        coverage = ScopeCoverage(
            provider=CloudProvider.AZURE,
            account_id=subscription,
            region=region,
            service=service,
            status=coverage_status_for(len(resources), errors),
            resources_discovered=len(resources),
            resources_inspected=len(resources),
            errors=errors,
        )
        return resources, coverage

    @staticmethod
    def _base_resource(
        item: dict, subscription: str, region: str, service: str, resource_type: str, **extra
    ) -> Resource:
        return Resource(
            provider=CloudProvider.AZURE,
            account_id=subscription,
            region=region,
            service=service,
            resource_type=resource_type,
            native_id=item["id"],
            name=item["name"],
            tags=item.get("tags") or {},
            **extra,
        )

    def _build_cognitive_account(self, item: dict, subscription: str, region: str) -> Resource:
        return self._base_resource(
            item, subscription, region, "cognitiveservices", "account",
            config={"kind": item.get("kind"), "sku": item.get("sku", {}).get("name")},
        )

    def _build_ml_workspace(self, item: dict, subscription: str, region: str) -> Resource:
        return self._base_resource(
            item, subscription, region, "machinelearningservices", "workspace"
        )

    def _build_search_service(self, item: dict, subscription: str, region: str) -> Resource:
        return self._base_resource(
            item, subscription, region, "search", "search_service",
            config={"sku": item.get("sku", {}).get("name")},
        )

    def _build_web_app(self, item: dict, subscription: str, region: str) -> Resource:
        settings = item.get("properties", {}).get("siteConfig", {}).get("appSettings", [])
        # Setting values are never read. Only the names are kept.
        setting_names = sorted({entry["name"] for entry in settings})
        return self._base_resource(
            item, subscription, region, "web", "site",
            env_var_names=setting_names,
            config={"kind": item.get("kind")},
        )

    def _build_virtual_machine(self, item: dict, subscription: str, region: str) -> Resource:
        properties = item.get("properties", {})
        return self._base_resource(
            item, subscription, region, "compute", "virtual_machine",
            created_at=_parse_time(properties.get("timeCreated")),
            config={"instance_type": properties.get("hardwareProfile", {}).get("vmSize")},
        )

    def _build_secret(self, item: dict, subscription: str, region: str) -> Resource:
        return self._base_resource(item, subscription, region, "keyvault", "secret")