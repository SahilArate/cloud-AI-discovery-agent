"""Looks up who created a resource in CloudTrail. A hint only, never a verified owner."""

import json
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ai_discovery.models.resource import Resource

# (service, resource_type) -> (CloudTrail event name, key to look the resource up by)
_CREATE_EVENTS = {
    ("lambda", "function"): ("CreateFunction20150331", "name"),
    ("sagemaker", "endpoint"): ("CreateEndpoint", "name"),
    ("sagemaker", "notebook_instance"): ("CreateNotebookInstance", "name"),
}

LOOKBACK_DAYS = 90  # CloudTrail event history limit


def _identity_name(user_identity: dict) -> str | None:
    """A readable name from a CloudTrail userIdentity block, without credentials."""
    identity_type = user_identity.get("type")
    if identity_type == "IAMUser":
        return user_identity.get("userName")
    if identity_type == "AssumedRole":
        # arn:aws:sts::123456789012:assumed-role/ROLE_NAME/SESSION_NAME
        arn = user_identity.get("arn", "")
        parts = arn.split("/")
        return parts[1] if len(parts) >= 3 else None
    return None


def find_creator(session: boto3.Session, resource: Resource) -> str | None:
    """Name of the identity that created the resource, or None if CloudTrail can't say."""
    entry = _CREATE_EVENTS.get((resource.service, resource.resource_type))
    if entry is None:
        return None
    event_name, _ = entry

    end = datetime.now(timezone.utc)
    try:
        client = session.client("cloudtrail", region_name=resource.region)
        response = client.lookup_events(
            LookupAttributes=[{"AttributeKey": "ResourceName", "AttributeValue": resource.name}],
            StartTime=end - timedelta(days=LOOKBACK_DAYS),
            EndTime=end,
            MaxResults=50,
        )
    except (ClientError, BotoCoreError):
        return None

    for event in response.get("Events", []):
        if event.get("EventName") != event_name:
            continue
        try:
            detail = json.loads(event["CloudTrailEvent"])
        except (KeyError, ValueError):
            continue
        name = _identity_name(detail.get("userIdentity", {}))
        if name:
            return name
    return None