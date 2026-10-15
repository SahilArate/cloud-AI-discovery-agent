"""Deterministic verdict rules: evidence in, Finding out. No LLM involved."""

from ai_discovery.models.enums import AIVerdict, EvidenceStrength
from ai_discovery.models.evidence import Evidence
from ai_discovery.models.finding import Finding
from ai_discovery.models.resource import Resource


def _describe(evidence: list[Evidence]) -> str:
    return "; ".join(item.detail for item in evidence)


def classify(resource: Resource, evidence: list[Evidence]) -> Finding:
    """Decide whether a resource is AI-related, using only the evidence given.

    Activity is not decided here. It stays unknown until enrichment looks at usage.
    """
    strong = [item for item in evidence if item.strength == EvidenceStrength.STRONG]
    supporting = [item for item in evidence if item.strength == EvidenceStrength.SUPPORTING]
    weak = [item for item in evidence if item.strength == EvidenceStrength.WEAK]

    # Strong evidence (a managed AI service, a confirmed model call) is enough on its own.
    if strong:
        return Finding(
            asset_key=resource.asset_key,
            verdict=AIVerdict.AI_CONFIRMED,
            evidence=evidence,
            reasoning=f"Strong evidence of AI: {_describe(strong)}.",
        )

    # Leads such as an API key name or an AI package are not proof the AI is ever called.
    if supporting:
        return Finding(
            asset_key=resource.asset_key,
            verdict=AIVerdict.AI_SUSPECTED,
            evidence=evidence,
            reasoning=f"Credible signals but no proof of use: {_describe(supporting + weak)}.",
            missing_evidence=["runtime_invocations"],
            review_required=True,
        )

    # Weak signals alone (a GPU type, a name) are too thin to call it AI either way.
    if weak:
        return Finding(
            asset_key=resource.asset_key,
            verdict=AIVerdict.UNKNOWN,
            evidence=evidence,
            reasoning=f"Only weak signals found: {_describe(weak)}.",
            missing_evidence=["managed_ai_resource", "runtime_invocations"],
            review_required=True,
        )

    return Finding(
        asset_key=resource.asset_key,
        verdict=AIVerdict.NOT_AI_EVIDENCED,
        reasoning="No AI evidence found in the data we inspected. This does not prove AI is absent.",
    )