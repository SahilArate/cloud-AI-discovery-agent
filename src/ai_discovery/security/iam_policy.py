"""Builds the least-privilege, read-only AWS IAM policy from the discovery catalog."""

import json

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.models.enums import CloudProvider

# Calls the collectors make that are not listing operations in the catalog.
SUPPORTING_ACTIONS = [
    "lambda:ListTags",
    "sagemaker:ListTags",
    "cloudwatch:GetMetricStatistics",
    "cloudtrail:LookupEvents",
]

# In the catalog, but no collector calls them yet, so they are not granted.
NOT_COLLECTED_YET = {"bedrock:ListProvisionedModelThroughputs"}

# Denied even if some other policy on the role would allow them.
NEVER_ALLOW = [
    "secretsmanager:GetSecretValue",
    "ssm:GetParameter",
    "ssm:GetParameters",
]


def allowed_actions() -> list[str]:
    catalog = load_catalog(CloudProvider.AWS)
    listed = set(catalog.read_operations()) - NOT_COLLECTED_YET
    return sorted(listed | set(SUPPORTING_ACTIONS))


def build_aws_policy() -> dict:
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "DiscoveryReadOnly",
                "Effect": "Allow",
                "Action": allowed_actions(),
                "Resource": "*",
            },
            {
                "Sid": "NeverReadSecretValues",
                "Effect": "Deny",
                "Action": NEVER_ALLOW,
                "Resource": "*",
            },
        ],
    }


if __name__ == "__main__":
    print(json.dumps(build_aws_policy(), indent=2))