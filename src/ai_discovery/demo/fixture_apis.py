"""Fixture-driven GCP and Azure APIs for demos. Realistic shapes, invented data."""

GCP_PROJECT = "demo-project"
GCP_REGION = "asia-south1"

AZURE_SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"
AZURE_REGION = "centralindia"
_AZURE_BASE = f"/subscriptions/{AZURE_SUBSCRIPTION}/resourceGroups/rg-demo/providers"


class DemoGCPApi:
    def list_vertex_endpoints(self, project, region):
        return [
            {
                "name": f"projects/{project}/locations/{region}/endpoints/support-bot",
                "displayName": "support-bot",
                "labels": {"owner": "ml-platform"},
                "createTime": "2026-08-12T09:30:00+00:00",
                "deployedModels": [{"id": "1"}],
            }
        ]

    def list_cloud_run_services(self, project, region):
        return [
            {
                "name": f"projects/{project}/locations/{region}/services/doc-summariser",
                "template": {
                    "containers": [
                        {
                            "image": "gcr.io/demo/summariser:latest",
                            "env": [
                                {"name": "GEMINI_API_KEY", "value": "demo-not-a-real-key"},
                                {"name": "LOG_LEVEL", "value": "info"},
                            ],
                        }
                    ]
                },
            }
        ]

    def list_compute_instances(self, project, region):
        return [
            {
                "name": "training-box",
                "zone": f"https://www.googleapis.com/compute/v1/projects/{project}/zones/{region}-a",
                "machineType": f".../zones/{region}-a/machineTypes/a2-highgpu-1g",
                "status": "RUNNING",
            }
        ]

    def list_secrets(self, project):
        return [{"name": f"projects/{project}/secrets/GOOGLE_API_KEY"}]


class DemoAzureApi:
    def list_cognitive_accounts(self, subscription, region):
        return [
            {
                "id": f"{_AZURE_BASE}/Microsoft.CognitiveServices/accounts/contoso-openai",
                "name": "contoso-openai",
                "kind": "OpenAI",
                "sku": {"name": "S0"},
                "tags": {"owner": "data-science"},
            }
        ]

    def list_ml_workspaces(self, subscription, region):
        return []

    def list_search_services(self, subscription, region):
        return [
            {
                "id": f"{_AZURE_BASE}/Microsoft.Search/searchServices/docs-index",
                "name": "docs-index",
                "sku": {"name": "standard"},
            }
        ]

    def list_web_apps(self, subscription, region):
        return [
            {
                "id": f"{_AZURE_BASE}/Microsoft.Web/sites/hr-assistant",
                "name": "hr-assistant",
                "kind": "functionapp",
                "properties": {
                    "siteConfig": {
                        "appSettings": [
                            {"name": "AZURE_OPENAI_API_KEY", "value": "demo-not-a-real-key"},
                            {"name": "WEBSITE_RUN_FROM_PACKAGE", "value": "1"},
                        ]
                    }
                },
            }
        ]

    def list_virtual_machines(self, subscription, region):
        return [
            {
                "id": f"{_AZURE_BASE}/Microsoft.Compute/virtualMachines/render-node",
                "name": "render-node",
                "properties": {"hardwareProfile": {"vmSize": "Standard_NC24ads_A100_v4"}},
            }
        ]

    def list_key_vault_secrets(self, subscription, region):
        return []