"""Hand-labelled expectations for the demo estate. Every label has a reason a human can check."""

from pydantic import BaseModel

from ai_discovery.models.enums import AIVerdict, ApprovalStatus


class ExpectedAsset(BaseModel):
    asset_key: str
    verdict: AIVerdict
    approval: ApprovalStatus
    reason: str


_AWS = "aws:arn:aws"
_ACCT = "123456789012"
_AZ_BASE = (
    "azure:/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/rg-demo/providers"
)


# Resources that are plain and must NOT be flagged. Listed by key prefix, since moto
# gives EC2 instances and secrets random suffixes.
EXPECTED_NOT_AI = [
    f"{_AWS}:lambda:ap-south-1:{_ACCT}:function:report-builder",
    f"{_AWS}:lambda:ap-south-1:{_ACCT}:function:image-resizer",
]

EXPECTED_ASSETS = [
    # ---- AWS ----
    ExpectedAsset(
        asset_key=f"{_AWS}:lambda:ap-south-1:{_ACCT}:function:approved-summariser",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.APPROVED,
        reason="Only an ANTHROPIC_API_KEY name (a lead), but registered as AI-001.",
    ),
    ExpectedAsset(
        asset_key=f"{_AWS}:sagemaker:ap-south-1:{_ACCT}:endpoint/churn-predictor",
        verdict=AIVerdict.AI_CONFIRMED,
        approval=ApprovalStatus.APPROVED,
        reason="SageMaker endpoint, registered as AI-002.",
    ),
    ExpectedAsset(
        asset_key=f"{_AWS}:lambda:ap-south-1:{_ACCT}:function:invoice-helper",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="OPENAI_API_KEY name only, not in the register.",
    ),
    ExpectedAsset(
        asset_key=f"{_AWS}:sagemaker:ap-south-1:{_ACCT}:endpoint/shadow-embeddings",
        verdict=AIVerdict.AI_CONFIRMED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="SageMaker endpoint nobody registered.",
    ),
    ExpectedAsset(
        asset_key=f"{_AWS}:sagemaker:us-east-1:{_ACCT}:notebook-instance/research-notebook",
        verdict=AIVerdict.AI_CONFIRMED,
        approval=ApprovalStatus.GOVERNANCE_EXCEPTION,
        reason="Registered as AI-003 for ap-south-1 but running in us-east-1.",
    ),
    # ---- GCP ----
    ExpectedAsset(
        asset_key="gcp:projects/demo-project/locations/asia-south1/endpoints/support-bot",
        verdict=AIVerdict.AI_CONFIRMED,
        approval=ApprovalStatus.APPROVED,
        reason="Vertex AI endpoint, registered as AI-004.",
    ),
    ExpectedAsset(
        asset_key="gcp:projects/demo-project/locations/asia-south1/services/doc-summariser",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="GEMINI_API_KEY name only, not in the register.",
    ),
    ExpectedAsset(
        asset_key="gcp:projects/demo-project/zones/asia-south1-a/instances/training-box",
        verdict=AIVerdict.UNKNOWN,
        approval=ApprovalStatus.NOT_ASSESSED,
        reason="A GPU machine type alone is weak evidence, so we do not guess.",
    ),
    ExpectedAsset(
        asset_key="gcp:projects/demo-project/secrets/GOOGLE_API_KEY",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="A secret named like an AI key is a lead.",
    ),
    # ---- Azure ----
    ExpectedAsset(
        asset_key=f"{_AZ_BASE}/Microsoft.CognitiveServices/accounts/contoso-openai",
        verdict=AIVerdict.AI_CONFIRMED,
        approval=ApprovalStatus.APPROVED,
        reason="Azure OpenAI account, registered as AI-005.",
    ),
    ExpectedAsset(
        asset_key=f"{_AZ_BASE}/Microsoft.Search/searchServices/docs-index",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="AI Search alone is only a hint of RAG, and it is unregistered.",
    ),
    ExpectedAsset(
        asset_key=f"{_AZ_BASE}/Microsoft.Web/sites/hr-assistant",
        verdict=AIVerdict.AI_SUSPECTED,
        approval=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason="AZURE_OPENAI_API_KEY setting name only, unregistered.",
    ),
    ExpectedAsset(
        asset_key=f"{_AZ_BASE}/Microsoft.Compute/virtualMachines/render-node",
        verdict=AIVerdict.UNKNOWN,
        approval=ApprovalStatus.NOT_ASSESSED,
        reason="A GPU VM size alone is weak evidence.",
    ),
]

# Resources whose keys carry random suffixes in moto, matched by prefix instead.
# Each pair is (key prefix, expected verdict, expected approval).
EXPECTED_BY_PREFIX = [
    (
        f"{_AWS}:secretsmanager:ap-south-1:{_ACCT}:secret:OPENAI_API_KEY",
        AIVerdict.AI_SUSPECTED,
        ApprovalStatus.POTENTIAL_SHADOW_AI,
    ),
    (
        f"{_AWS}:ec2:ap-south-1:{_ACCT}:instance/",
        AIVerdict.UNKNOWN,
        ApprovalStatus.NOT_ASSESSED,
    ),
]