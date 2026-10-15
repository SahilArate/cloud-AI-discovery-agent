"""Decides approval status, reason codes and risk tier for a classified asset."""

from enum import Enum

from pydantic import BaseModel, Field

from ai_discovery.governance.register import MatchIssue, MatchResult, RegisterMatch
from ai_discovery.models.enums import AIVerdict, ApprovalStatus, OwnerSource, RiskTier
from ai_discovery.models.finding import Finding


class ReasonCode(str, Enum):
    NOT_IN_APPROVED_REGISTER = "not_in_approved_register"
    OWNER_UNVERIFIED = "owner_unverified"
    AI_USE_UNCONFIRMED = "ai_use_unconfirmed"
    ACCOUNT_MISMATCH = "account_mismatch"
    REGION_NOT_APPROVED = "region_not_approved"
    OWNER_MISMATCH = "owner_mismatch"


# Register issues map one-to-one onto reason codes.
_ISSUE_TO_REASON = {
    MatchIssue.ACCOUNT_MISMATCH: ReasonCode.ACCOUNT_MISMATCH,
    MatchIssue.REGION_NOT_APPROVED: ReasonCode.REGION_NOT_APPROVED,
    MatchIssue.OWNER_MISMATCH: ReasonCode.OWNER_MISMATCH,
}


class ShadowAssessment(BaseModel):
    approval_status: ApprovalStatus
    reason_codes: list[ReasonCode] = Field(default_factory=list)
    risk_tier: RiskTier
    next_action: str = ""


def assess(finding: Finding, match: MatchResult, owner_source: OwnerSource) -> ShadowAssessment:
    """Apply the approval policy.

    Risk policy:
      - approved and in scope                         -> low
      - registered but outside its approved scope     -> medium
      - not registered, AI confirmed, owner unverified -> high
      - not registered, anything else                 -> medium
    """
    # Approval only applies to things we believe are AI. Everything else is not assessed.
    if finding.verdict not in (AIVerdict.AI_CONFIRMED, AIVerdict.AI_SUSPECTED):
        return ShadowAssessment(
            approval_status=ApprovalStatus.NOT_ASSESSED,
            risk_tier=RiskTier.UNASSESSED,
        )

    if match.outcome == RegisterMatch.MATCHED:
        return ShadowAssessment(approval_status=ApprovalStatus.APPROVED, risk_tier=RiskTier.LOW)

    if match.outcome == RegisterMatch.OUT_OF_SCOPE:
        return ShadowAssessment(
            approval_status=ApprovalStatus.GOVERNANCE_EXCEPTION,
            reason_codes=[_ISSUE_TO_REASON[issue] for issue in match.issues],
            risk_tier=RiskTier.MEDIUM,
            next_action="Confirm with the owner whether this change was approved.",
        )

    # Not in the register: potential shadow AI.
    reasons = [ReasonCode.NOT_IN_APPROVED_REGISTER]
    owner_unverified = owner_source != OwnerSource.EXPLICIT_TAG
    if owner_unverified:
        reasons.append(ReasonCode.OWNER_UNVERIFIED)
    if finding.verdict == AIVerdict.AI_SUSPECTED:
        reasons.append(ReasonCode.AI_USE_UNCONFIRMED)

    confirmed = finding.verdict == AIVerdict.AI_CONFIRMED
    risk = RiskTier.HIGH if (confirmed and owner_unverified) else RiskTier.MEDIUM

    return ShadowAssessment(
        approval_status=ApprovalStatus.POTENTIAL_SHADOW_AI,
        reason_codes=reasons,
        risk_tier=risk,
        next_action="Verify the owner and check whether a business approval exists.",
    )