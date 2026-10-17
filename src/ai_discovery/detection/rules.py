"""Rules that turn a Resource into evidence records. No LLM, no verdicts."""

import re

from ai_discovery.catalog.loader import Catalog
from ai_discovery.models.enums import EvidenceStrength, EvidenceType
from ai_discovery.models.evidence import Evidence
from ai_discovery.models.resource import Resource

# Names are split into words so "rag" matches "invoice-rag-helper" but not "storage".
_WORD_SPLIT = re.compile(r"[-_./\s]+")


def _make_evidence(
    resource: Resource,
    evidence_type: EvidenceType,
    strength: EvidenceStrength,
    source: str,
    detail: str,
) -> Evidence:
    return Evidence(
        asset_key=resource.asset_key,
        evidence_type=evidence_type,
        strength=strength,
        source=source,
        detail=detail,
    )


def _managed_service_evidence(resource: Resource, catalog: Catalog) -> list[Evidence]:
    for entry in catalog.managed_ai_services:
        if entry.service == resource.service and entry.resource_type == resource.resource_type:
            return [
                _make_evidence(
                    resource,
                    entry.evidence_type,
                    entry.strength,
                    source="discovery_catalog",
                    detail=f"{entry.service} {entry.resource_type} is an AI service by nature",
                )
            ]
    return []


def _secret_name_evidence(resource: Resource, catalog: Catalog) -> list[Evidence]:
    known_names = {name.upper() for name in catalog.signals.ai_secret_name_patterns}
    found: list[Evidence] = []

    for env_name in resource.env_var_names:
        if env_name.upper() in known_names:
            found.append(
                _make_evidence(
                    resource,
                    EvidenceType.AI_SECRET_NAME,
                    EvidenceStrength.SUPPORTING,
                    source=f"{resource.service}_config",
                    detail=f"env var name {env_name}",
                )
            )

    if resource.resource_type == "secret" and resource.name.upper() in known_names:
        found.append(
            _make_evidence(
                resource,
                EvidenceType.AI_SECRET_NAME,
                EvidenceStrength.SUPPORTING,
                source=f"{resource.service}_listing",
                detail=f"secret named {resource.name}",
            )
        )
    return found


def _gpu_evidence(resource: Resource, catalog: Catalog) -> list[Evidence]:
    instance_type = resource.config.get("instance_type")
    if not isinstance(instance_type, str):
        return []

    # SageMaker types look like "ml.g5.xlarge"; the family is the "g5" part.
    family = instance_type.removeprefix("ml.").split(".")[0].lower()
    if any(family.startswith(prefix) for prefix in catalog.signals.gpu_instance_prefixes):
        return [
            _make_evidence(
                resource,
                EvidenceType.GPU_INSTANCE_TYPE,
                EvidenceStrength.WEAK,  # GPUs also run non-AI work
                source=f"{resource.service}_config",
                detail=f"instance type {instance_type}",
            )
        ]
    return []


def _name_hint_evidence(resource: Resource, catalog: Catalog) -> list[Evidence]:
    words = set(_WORD_SPLIT.split(resource.name.lower()))
    hits = sorted(words & {hint.lower() for hint in catalog.signals.name_hints})
    if not hits:
        return []
    return [
        _make_evidence(
            resource,
            EvidenceType.NAME_HINT,
            EvidenceStrength.WEAK,  # names can be misleading
            source="resource_name",
            detail=f"name contains {', '.join(hits)}",
        )
    ]


def gather_evidence(resource: Resource, catalog: Catalog) -> list[Evidence]:
    """Every clue we can find for one resource, in a fixed order."""
    return [
        *_managed_service_evidence(resource, catalog),
        *_secret_name_evidence(resource, catalog),
        *_gpu_evidence(resource, catalog),
        *_name_hint_evidence(resource, catalog),
    ]