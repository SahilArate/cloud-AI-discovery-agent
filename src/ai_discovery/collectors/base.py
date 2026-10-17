"""Common interface for cloud collectors."""

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field

from ai_discovery.models.coverage import ScopeCoverage
from ai_discovery.models.enums import CloudProvider
from ai_discovery.models.resource import Resource
from ai_discovery.models.coverage import CollectionError, ScopeCoverage
from ai_discovery.models.enums import CloudProvider, CoverageStatus


class ScanScope(BaseModel):
    """What the client allowed us to look at."""

    account_id: str
    regions: list[str]


class CollectionResult(BaseModel):
    """Resources found plus a record of what we could and couldn't inspect."""

    resources: list[Resource] = Field(default_factory=list)
    coverage: list[ScopeCoverage] = Field(default_factory=list)


class BaseCollector(ABC):
    """Collectors only read. They never classify, and they never call an LLM."""

    provider: CloudProvider

    @abstractmethod
    def collect(self, scope: ScanScope) -> CollectionResult:
        """List resources in the scope. A failure in one service must not stop the others:
        record it as a ScopeCoverage with errors and carry on."""

    def read_usage(self, resource: Resource) -> int | None:
        """Calls in the last 30 days, or None if this collector can't measure it."""
        return None

def coverage_status_for(discovered: int, errors: list[CollectionError]) -> CoverageStatus:
    """Complete with no errors, failed if nothing was found and something broke, else partial."""
    if not errors:
        return CoverageStatus.COMPLETE
    if discovered == 0:
        return CoverageStatus.FAILED
    return CoverageStatus.PARTIAL