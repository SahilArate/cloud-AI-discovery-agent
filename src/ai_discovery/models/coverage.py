"""What a scan inspected, skipped or failed on, so gaps are visible."""

from pydantic import BaseModel, Field, model_validator

from ai_discovery.models.enums import CloudProvider, CoverageStatus


class CollectionError(BaseModel):
    code: str  # e.g. "ACCESS_DENIED", "THROTTLED", "UNSUPPORTED_SERVICE"
    operation: str  # the API call that failed, e.g. "sagemaker:ListEndpoints"
    message: str = ""  # short and safe to log, never raw credentials or payloads


class ScopeCoverage(BaseModel):
    """Result of inspecting one scope: a provider, account, region and service."""

    provider: CloudProvider
    account_id: str
    region: str
    service: str
    status: CoverageStatus
    resources_discovered: int = 0
    resources_inspected: int = 0
    errors: list[CollectionError] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_counts(self) -> "ScopeCoverage":
        if self.resources_inspected > self.resources_discovered:
            raise ValueError("resources_inspected cannot exceed resources_discovered")
        return self

    @property
    def scope_label(self) -> str:
        return f"{self.provider.value}/{self.account_id}/{self.region}/{self.service}"

    @property
    def is_gap(self) -> bool:
        """True when we could not fully see this scope."""
        return self.status != CoverageStatus.COMPLETE