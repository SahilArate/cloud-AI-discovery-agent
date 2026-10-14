"""Normalised view of a cloud resource, produced by every collector."""

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from ai_discovery.models.enums import CloudProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Resource(BaseModel):
    provider: CloudProvider
    account_id: str
    region: str
    service: str  # e.g. "lambda", "sagemaker", "bedrock"
    resource_type: str  # e.g. "function", "endpoint", "instance"
    native_id: str  # the cloud's own identifier, an ARN on AWS
    name: str
    tags: dict[str, str] = Field(default_factory=dict)
    created_at: datetime | None = None

    # Names only, never values. Secrets must not enter the pipeline.
    env_var_names: list[str] = Field(default_factory=list)

    # Redacted service-specific metadata (instance type, runtime, layers, ...)
    config: dict[str, Any] = Field(default_factory=dict)

    collected_at: datetime = Field(default_factory=_utc_now)

    @property
    def asset_key(self) -> str:
        """Stable identity across scans, so we can tell new from already-seen."""
        return f"{self.provider.value}:{self.native_id}"