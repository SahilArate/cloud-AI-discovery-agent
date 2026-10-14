"""Shared vocabulary used across collectors, detection, governance and storage."""

from enum import Enum


class CloudProvider(str, Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


class AIVerdict(str, Enum):
    """Is this resource AI-related? Based only on the evidence we collected."""

    AI_CONFIRMED = "ai_confirmed"
    AI_SUSPECTED = "ai_suspected"
    NOT_AI_EVIDENCED = "not_ai_evidenced"  # no AI evidence found, not proof of absence
    UNKNOWN = "unknown"


class ActivityStatus(str, Enum):
    """Is it being used? Kept separate so an idle endpoint is still AI."""

    ACTIVE_OBSERVED = "active_observed"
    DORMANT_OBSERVED = "dormant_observed"
    NO_ACTIVITY_OBSERVED = "no_activity_observed"
    ACTIVITY_UNKNOWN = "activity_unknown"


class EvidenceType(str, Enum):
    MANAGED_AI_RESOURCE = "managed_ai_resource"
    MODEL_INVOCATION = "model_invocation"
    EXTERNAL_API_CALL = "external_api_call"
    AI_DEPENDENCY = "ai_dependency"
    AI_IAM_PERMISSION = "ai_iam_permission"
    AI_SECRET_NAME = "ai_secret_name"
    GPU_INSTANCE_TYPE = "gpu_instance_type"
    NAME_HINT = "name_hint"


class EvidenceStrength(str, Enum):
    STRONG = "strong"
    SUPPORTING = "supporting"
    WEAK = "weak"


class OwnerSource(str, Enum):
    """Where an owner value came from. A creator is a hint, not the owner."""

    EXPLICIT_TAG = "explicit_tag"
    INFERRED_CREATOR = "inferred_creator"
    UNKNOWN = "unknown"


class ApprovalStatus(str, Enum):
    """Is it approved? Answered separately from the AI verdict."""

    APPROVED = "approved"
    POTENTIAL_SHADOW_AI = "potential_shadow_ai"
    GOVERNANCE_EXCEPTION = "governance_exception"  # registered, but outside approved scope
    NOT_ASSESSED = "not_assessed"


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNASSESSED = "unassessed"


class ReviewStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    ESCALATED = "escalated"


class CoverageStatus(str, Enum):
    """Outcome of inspecting one scope (account, region, service)."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"