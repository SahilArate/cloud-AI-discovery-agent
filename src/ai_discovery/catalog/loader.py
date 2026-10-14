"""Loads and validates the per-cloud discovery catalogs."""

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_discovery.models.enums import CloudProvider, EvidenceStrength, EvidenceType

CATALOG_DIR = Path(__file__).parent


class ManagedAIService(BaseModel):
    service: str
    resource_type: str
    list_operation: str
    evidence_type: EvidenceType
    strength: EvidenceStrength
    usage_source: str = "none"


class ComputeService(BaseModel):
    service: str
    resource_type: str
    list_operation: str
    inspect_fields: list[str] = Field(default_factory=list)
    usage_source: str = "none"


class IdentityService(BaseModel):
    service: str
    resource_type: str
    list_operation: str
    inspect_fields: list[str] = Field(default_factory=list)


class Signals(BaseModel):
    ai_secret_name_patterns: list[str] = Field(default_factory=list)
    ai_dependency_names: list[str] = Field(default_factory=list)
    gpu_instance_prefixes: list[str] = Field(default_factory=list)
    name_hints: list[str] = Field(default_factory=list)


class Catalog(BaseModel):
    catalog_version: str
    provider: CloudProvider
    managed_ai_services: list[ManagedAIService] = Field(default_factory=list)
    compute_services: list[ComputeService] = Field(default_factory=list)
    identity_services: list[IdentityService] = Field(default_factory=list)
    signals: Signals = Field(default_factory=Signals)

    def read_operations(self) -> list[str]:
        """Every API call this catalog allows, e.g. 'lambda:ListFunctions'.
        This is the list the read-only IAM policy has to match."""
        groups = [self.managed_ai_services, self.compute_services, self.identity_services]
        return sorted(
            f"{item.service}:{item.list_operation}" for group in groups for item in group
        )


@lru_cache
def load_catalog(provider: CloudProvider) -> Catalog:
    path = CATALOG_DIR / f"{provider.value}.yaml"
    with path.open(encoding="utf-8") as handle:
        return Catalog.model_validate(yaml.safe_load(handle))