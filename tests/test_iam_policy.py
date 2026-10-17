"""IAM policy tests: read-only, no secret values, and in sync with the catalog."""

import json
from pathlib import Path

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.models.enums import CloudProvider
from ai_discovery.security.iam_policy import (
    NOT_COLLECTED_YET,
    NEVER_ALLOW,
    allowed_actions,
    build_aws_policy,
)

POLICY_FILE = Path(__file__).resolve().parent.parent / "docs" / "aws-readonly-policy.json"
READ_PREFIXES = ("List", "Describe", "Get", "Lookup")


def test_every_allowed_action_is_read_only():
    for action in allowed_actions():
        verb = action.split(":", 1)[1]
        assert verb.startswith(READ_PREFIXES), action


def test_secret_values_are_denied_and_never_allowed():
    policy = build_aws_policy()
    allow = next(s for s in policy["Statement"] if s["Effect"] == "Allow")
    deny = next(s for s in policy["Statement"] if s["Effect"] == "Deny")

    for action in NEVER_ALLOW:
        assert action not in allow["Action"]
        assert action in deny["Action"]


def test_every_catalog_operation_is_granted_unless_not_collected_yet():
    catalog_ops = set(load_catalog(CloudProvider.AWS).read_operations())

    assert catalog_ops - NOT_COLLECTED_YET <= set(allowed_actions())
    assert not NOT_COLLECTED_YET & set(allowed_actions())


def test_committed_policy_file_matches_the_catalog():
    committed = json.loads(POLICY_FILE.read_text(encoding="utf-8"))

    assert committed == build_aws_policy()