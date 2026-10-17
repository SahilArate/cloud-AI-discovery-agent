"""Azure collector tests: a fake AzureApi returns ARM-shaped responses."""

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.collectors.azure import AzureApiError, AzureCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.detection.classifier import classify
from ai_discovery.detection.rules import gather_evidence
from ai_discovery.models.enums import AIVerdict, CloudProvider, CoverageStatus

SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
REGION = "centralindia"
FAKE_SECRET_VALUE = "sk-test-not-a-real-key"
BASE = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/rg-demo/providers"


class FakeAzureApi:
    def __init__(self, accounts=None, workspaces=None, searches=None,
                 web_apps=None, vms=None, secrets=None, deny=()):
        self._data = {
            "cognitive": accounts or [],
            "ml": workspaces or [],
            "search": searches or [],
            "web": web_apps or [],
            "vm": vms or [],
            "secrets": secrets or [],
        }
        self._deny = set(deny)

    def _get(self, key):
        if key in self._deny:
            raise AzureApiError("AuthorizationFailed")
        return self._data[key]

    def list_cognitive_accounts(self, subscription, region):
        return self._get("cognitive")

    def list_ml_workspaces(self, subscription, region):
        return self._get("ml")

    def list_search_services(self, subscription, region):
        return self._get("search")

    def list_web_apps(self, subscription, region):
        return self._get("web")

    def list_virtual_machines(self, subscription, region):
        return self._get("vm")

    def list_key_vault_secrets(self, subscription, region):
        return self._get("secrets")


def _collect(api: FakeAzureApi):
    scope = ScanScope(account_id=SUBSCRIPTION, regions=[REGION])
    return AzureCollector(api).collect(scope)


def _judge(resource):
    catalog = load_catalog(CloudProvider.AZURE)
    return classify(resource, gather_evidence(resource, catalog))


def _openai_account(name="contoso-openai", tags=None):
    return {
        "id": f"{BASE}/Microsoft.CognitiveServices/accounts/{name}",
        "name": name,
        "kind": "OpenAI",
        "sku": {"name": "S0"},
        "tags": tags,
    }


def _web_app(name="invoice-helper", settings=None):
    return {
        "id": f"{BASE}/Microsoft.Web/sites/{name}",
        "name": name,
        "kind": "functionapp",
        "properties": {
            "siteConfig": {
                "appSettings": [
                    {"name": key, "value": value} for key, value in (settings or {}).items()
                ]
            }
        },
    }


def _vm(name="gpu-worker", size="Standard_NC24ads_A100_v4"):
    return {
        "id": f"{BASE}/Microsoft.Compute/virtualMachines/{name}",
        "name": name,
        "properties": {"hardwareProfile": {"vmSize": size}},
    }


def test_azure_openai_account_is_confirmed_ai_and_tags_are_kept():
    api = FakeAzureApi(accounts=[_openai_account(tags={"owner": "data-science"})])

    result = _collect(api)

    account = next(r for r in result.resources if r.service == "cognitiveservices")
    assert account.tags == {"owner": "data-science"}
    assert account.native_id.startswith("/subscriptions/")
    assert _judge(account).verdict == AIVerdict.AI_CONFIRMED


def test_missing_tags_become_an_empty_dict():
    result = _collect(FakeAzureApi(accounts=[_openai_account(tags=None)]))

    assert result.resources[0].tags == {}


def test_ai_search_alone_is_only_suspected():
    search = {"id": f"{BASE}/Microsoft.Search/searchServices/docs", "name": "docs",
              "sku": {"name": "standard"}}

    result = _collect(FakeAzureApi(searches=[search]))

    assert _judge(result.resources[0]).verdict == AIVerdict.AI_SUSPECTED


def test_web_app_keeps_setting_names_but_never_values():
    api = FakeAzureApi(
        web_apps=[_web_app(settings={"OPENAI_API_KEY": FAKE_SECRET_VALUE, "LOG_LEVEL": "info"})]
    )

    result = _collect(api)

    site = next(r for r in result.resources if r.service == "web")
    assert site.env_var_names == ["LOG_LEVEL", "OPENAI_API_KEY"]
    assert FAKE_SECRET_VALUE not in result.model_dump_json()
    assert _judge(site).verdict == AIVerdict.AI_SUSPECTED


def test_gpu_vm_size_alone_is_unknown():
    result = _collect(FakeAzureApi(vms=[_vm()]))

    vm = next(r for r in result.resources if r.service == "compute")
    assert vm.config["instance_type"] == "Standard_NC24ads_A100_v4"
    assert _judge(vm).verdict == AIVerdict.UNKNOWN


def test_dashed_key_vault_secret_name_is_a_lead():
    secret = {"id": f"{BASE}/Microsoft.KeyVault/vaults/kv/secrets/OPENAI-API-KEY",
              "name": "OPENAI-API-KEY"}

    result = _collect(FakeAzureApi(secrets=[secret]))

    assert _judge(result.resources[0]).verdict == AIVerdict.AI_SUSPECTED


def test_clean_scan_reports_six_complete_scopes():
    result = _collect(FakeAzureApi())

    assert sorted(item.service for item in result.coverage) == [
        "cognitiveservices", "compute", "keyvault",
        "machinelearningservices", "search", "web",
    ]
    assert all(item.status == CoverageStatus.COMPLETE for item in result.coverage)


def test_authorization_failure_is_a_gap_and_other_services_still_work():
    api = FakeAzureApi(accounts=[_openai_account()], deny=("web",))

    result = _collect(api)

    web_scope = next(item for item in result.coverage if item.service == "web")
    assert web_scope.status == CoverageStatus.FAILED
    assert web_scope.errors[0].code == "AuthorizationFailed"
    assert web_scope.errors[0].operation == "web:ListSites"
    assert any(r.service == "cognitiveservices" for r in result.resources)