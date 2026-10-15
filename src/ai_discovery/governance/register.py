"""The approved AI register and the logic that matches discovered assets against it."""

from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ai_discovery.models.enums import CloudProvider
from ai_discovery.models.resource import Resource


class RegisterMatch(str, Enum):
    MATCHED = "matched"
    OUT_OF_SCOPE = "out_of_scope"  # registered, but something about it differs
    NOT_FOUND = "not_found"


class MatchIssue(str, Enum):
    ACCOUNT_MISMATCH = "account_mismatch"
    REGION_NOT_APPROVED = "region_not_approved"
    OWNER_MISMATCH = "owner_mismatch"


class ApprovedEntry(BaseModel):
    register_id: str
    name: str
    provider: CloudProvider
    account_id: str
    native_ids: list[str]  # one approved AI system can span several resources
    approved_regions: list[str] = Field(default_factory=list)  # empty means any region
    owner: str | None = None


class MatchResult(BaseModel):
    outcome: RegisterMatch
    entry: ApprovedEntry | None = None
    issues: list[MatchIssue] = Field(default_factory=list)


class ApprovedRegister(BaseModel):
    entries: list[ApprovedEntry] = Field(default_factory=list)

    def match(self, resource: Resource, owner: str | None = None) -> MatchResult:
        """Check one discovered resource against the register.

        owner is the owner we resolved during enrichment. It is only compared when both
        the register and the scan actually know an owner.
        """
        entry = self._find_entry(resource)
        if entry is None:
            return MatchResult(outcome=RegisterMatch.NOT_FOUND)

        issues: list[MatchIssue] = []
        if resource.account_id != entry.account_id:
            issues.append(MatchIssue.ACCOUNT_MISMATCH)
        if entry.approved_regions and resource.region not in entry.approved_regions:
            issues.append(MatchIssue.REGION_NOT_APPROVED)
        if owner and entry.owner and owner.lower() != entry.owner.lower():
            issues.append(MatchIssue.OWNER_MISMATCH)

        outcome = RegisterMatch.OUT_OF_SCOPE if issues else RegisterMatch.MATCHED
        return MatchResult(outcome=outcome, entry=entry, issues=issues)

    def _find_entry(self, resource: Resource) -> ApprovedEntry | None:
        for entry in self.entries:
            if entry.provider == resource.provider and resource.native_id in entry.native_ids:
                return entry
        return None


def load_register(path: Path) -> ApprovedRegister:
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return ApprovedRegister.model_validate(data)