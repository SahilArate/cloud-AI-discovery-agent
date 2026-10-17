"""One database, three clouds: GCP and Azure resources flow through the same pipeline."""

from sqlalchemy import func, select

from ai_discovery.collectors.azure import AzureCollector
from ai_discovery.collectors.base import ScanScope
from ai_discovery.collectors.gcp import GCPCollector
from ai_discovery.db.session import session_scope
from ai_discovery.db.tables import AIAsset, AssetObservation, ScanRun, ScanScopeResult
from ai_discovery.governance.register import ApprovedRegister
from ai_discovery.pipeline.scan import ScanTarget, run_scan, run_scan_targets

PROJECT = "demo-project"
SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"


class _EmptyGCPApi:
    def list_vertex_endpoints(self, project, region):
        return [{
            "name": f"projects/{project}/locations/{region}/endpoints/churn",
            "displayName": "churn",
        }]

    def list_cloud_run_services(self, project, region):
        return []

    def list_compute_instances(self, project, region):
        return []

    def list_secrets(self, project):
        return [{"name": f"projects/{project}/secrets/OPENAI_API_KEY"}]


class _EmptyAzureApi:
    def list_cognitive_accounts(self, subscription, region):
        return [{
            "id": f"/subscriptions/{subscription}/resourceGroups/rg/providers/"
                  "Microsoft.CognitiveServices/accounts/contoso-openai",
            "name": "contoso-openai",
            "kind": "OpenAI",
            "tags": {"owner": "data-science"},
        }]

    def list_ml_workspaces(self, subscription, region):
        return []

    def list_search_services(self, subscription, region):
        return []

    def list_web_apps(self, subscription, region):
        return []

    def list_virtual_machines(self, subscription, region):
        return []

    def list_key_vault_secrets(self, subscription, region):
        return []


def test_gcp_and_azure_land_in_the_same_inventory(test_database):
    register = ApprovedRegister()
    run_scan(GCPCollector(_EmptyGCPApi()),
             ScanScope(account_id=PROJECT, regions=["asia-south1"]), register)
    run_scan(AzureCollector(_EmptyAzureApi()),
             ScanScope(account_id=SUBSCRIPTION, regions=["centralindia"]), register)

    with session_scope() as session:
        providers = set(session.scalars(select(AIAsset.provider)).all())
        observations = session.scalars(select(AssetObservation)).all()
        by_asset = {obs.asset_key: obs for obs in observations}

    assert providers == {"gcp", "azure"}
    assert len(observations) == 3  # endpoint, secret, OpenAI account

    azure_obs = next(o for key, o in by_asset.items() if key.startswith("azure:"))
    assert azure_obs.ai_verdict == "ai_confirmed"
    assert azure_obs.owner == "data-science"
    assert azure_obs.owner_source == "explicit_tag"

    gcp_secret = next(o for key, o in by_asset.items() if key.endswith("secrets/OPENAI_API_KEY"))
    assert gcp_secret.ai_verdict == "ai_suspected"
    assert gcp_secret.approval_status == "potential_shadow_ai"

def test_three_clouds_share_one_scan_run(test_database):
    targets = [
        ScanTarget(GCPCollector(_EmptyGCPApi()),
                   ScanScope(account_id=PROJECT, regions=["asia-south1"])),
        ScanTarget(AzureCollector(_EmptyAzureApi()),
                   ScanScope(account_id=SUBSCRIPTION, regions=["centralindia"])),
    ]

    summary = run_scan_targets(targets, ApprovedRegister())

    with session_scope() as session:
        scan_count = session.scalar(select(func.count()).select_from(ScanRun))
        scope_providers = set(session.scalars(select(ScanScopeResult.provider)).all())
        scan_ids = set(session.scalars(select(AssetObservation.scan_id)).all())

    assert scan_count == 1
    assert scope_providers == {"gcp", "azure"}
    assert scan_ids == {summary.scan_id}
    assert summary.assets_recorded == 3