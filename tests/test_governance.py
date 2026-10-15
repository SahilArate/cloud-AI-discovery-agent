"""Governance tests: register matching and the shadow AI policy."""

import pytest

from ai_discovery.governance.register import (
    ApprovedEntry,
    ApprovedRegister,
    MatchIssue,
    RegisterMatch,
)
from ai_discovery.governance.shadow import ReasonCode, assess
from ai_discovery.models.enums import (
    AIVerdict,
    ApprovalStatus,
    CloudProvider,
    OwnerSource,
    RiskTier,
)
from ai_discovery.models.evidence import Evidence
from ai_discovery.models.finding import Finding
from ai_discovery.models.resource import Resource

ACCOUNT_ID = "123456789012"
APPROVED_ARN = "arn:aws:lambda:ap-south-1:123456789012:function:invoice-bot"


@pytest.fixture
def register() -> ApprovedRegister:
    return ApprovedRegister(
        entries=[
            ApprovedEntry(
                register_id="AI-001",
                name="Invoice bot",
                provider=CloudProvider.AWS,
                account_id=ACCOUNT_ID,
                native_ids=[APPROVED_ARN],
                approved_regions=["ap-south-1"],
                owner="finance-team",
            )
        ]
    )


def _make_resource(native_id: str = APPROVED_ARN, region: str = "ap-south-1",
                   account_id: str = ACCOUNT_ID) -> Resource:
    return Resource(
        provider=CloudProvider.AWS,
        account_id=account_id,
        region=region,
        service="lambda",
        resource_type="function",
        native_id=native_id,
        name="invoice-bot",
    )


def _make_finding(verdict: AIVerdict) -> Finding:
    evidence = []
    if verdict in (AIVerdict.AI_CONFIRMED, AIVerdict.AI_SUSPECTED):
        evidence = [
            Evidence(
                asset_key="aws:demo",
                evidence_type="managed_ai_resource",
                strength="strong",
                source="discovery_catalog",
                detail="demo",
            )
        ]
    return Finding(asset_key="aws:demo", verdict=verdict, evidence=evidence, reasoning="test")


# ---- register matching ----

def test_exact_resource_is_matched(register):
    result = register.match(_make_resource(), owner="finance-team")

    assert result.outcome == RegisterMatch.MATCHED
    assert result.issues == []


def test_unknown_resource_is_not_found(register):
    result = register.match(_make_resource(native_id="arn:other"))

    assert result.outcome == RegisterMatch.NOT_FOUND


def test_unapproved_region_is_out_of_scope(register):
    result = register.match(_make_resource(region="us-east-1"))

    assert result.outcome == RegisterMatch.OUT_OF_SCOPE
    assert result.issues == [MatchIssue.REGION_NOT_APPROVED]


def test_different_account_is_out_of_scope(register):
    result = register.match(_make_resource(account_id="999999999999"))

    assert MatchIssue.ACCOUNT_MISMATCH in result.issues


def test_owner_mismatch_is_reported(register):
    result = register.match(_make_resource(), owner="marketing-team")

    assert result.issues == [MatchIssue.OWNER_MISMATCH]


def test_unknown_owner_is_not_a_mismatch(register):
    result = register.match(_make_resource(), owner=None)

    assert result.outcome == RegisterMatch.MATCHED


# ---- shadow policy ----

def test_approved_asset_is_low_risk(register):
    match = register.match(_make_resource(), owner="finance-team")

    result = assess(_make_finding(AIVerdict.AI_CONFIRMED), match, OwnerSource.EXPLICIT_TAG)

    assert result.approval_status == ApprovalStatus.APPROVED
    assert result.risk_tier == RiskTier.LOW


def test_out_of_scope_is_a_governance_exception(register):
    match = register.match(_make_resource(region="us-east-1"))

    result = assess(_make_finding(AIVerdict.AI_CONFIRMED), match, OwnerSource.EXPLICIT_TAG)

    assert result.approval_status == ApprovalStatus.GOVERNANCE_EXCEPTION
    assert result.reason_codes == [ReasonCode.REGION_NOT_APPROVED]
    assert result.risk_tier == RiskTier.MEDIUM


def test_confirmed_unregistered_unowned_is_high_risk(register):
    match = register.match(_make_resource(native_id="arn:other"))

    result = assess(_make_finding(AIVerdict.AI_CONFIRMED), match, OwnerSource.UNKNOWN)

    assert result.approval_status == ApprovalStatus.POTENTIAL_SHADOW_AI
    assert result.reason_codes == [
        ReasonCode.NOT_IN_APPROVED_REGISTER,
        ReasonCode.OWNER_UNVERIFIED,
    ]
    assert result.risk_tier == RiskTier.HIGH


def test_unregistered_but_owned_is_medium_risk(register):
    match = register.match(_make_resource(native_id="arn:other"))

    result = assess(_make_finding(AIVerdict.AI_CONFIRMED), match, OwnerSource.EXPLICIT_TAG)

    assert result.reason_codes == [ReasonCode.NOT_IN_APPROVED_REGISTER]
    assert result.risk_tier == RiskTier.MEDIUM


def test_inferred_creator_does_not_count_as_verified_owner(register):
    match = register.match(_make_resource(native_id="arn:other"))

    result = assess(_make_finding(AIVerdict.AI_CONFIRMED), match, OwnerSource.INFERRED_CREATOR)

    assert ReasonCode.OWNER_UNVERIFIED in result.reason_codes


def test_suspected_ai_keeps_the_unconfirmed_reason(register):
    match = register.match(_make_resource(native_id="arn:other"))

    result = assess(_make_finding(AIVerdict.AI_SUSPECTED), match, OwnerSource.UNKNOWN)

    assert ReasonCode.AI_USE_UNCONFIRMED in result.reason_codes
    assert result.risk_tier == RiskTier.MEDIUM


def test_non_ai_resource_is_not_assessed(register):
    match = register.match(_make_resource(native_id="arn:other"))

    result = assess(_make_finding(AIVerdict.NOT_AI_EVIDENCED), match, OwnerSource.UNKNOWN)

    assert result.approval_status == ApprovalStatus.NOT_ASSESSED
    assert result.risk_tier == RiskTier.UNASSESSED