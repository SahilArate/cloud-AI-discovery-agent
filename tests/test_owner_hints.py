"""Owner hint tests: the identity parser, plus the full path through resolve_owner."""

import json

from ai_discovery.collectors.owner_hints_aws import _identity_name, find_creator
from ai_discovery.enrichment.owner import resolve_owner
from ai_discovery.models.enums import CloudProvider, OwnerSource
from ai_discovery.models.resource import Resource


def test_iam_user_name_is_used():
    assert _identity_name({"type": "IAMUser", "userName": "dev-ravi"}) == "dev-ravi"


def test_assumed_role_gives_the_role_name_not_the_session():
    identity = {
        "type": "AssumedRole",
        "arn": "arn:aws:sts::123456789012:assumed-role/ci-deployer/session-42",
    }
    assert _identity_name(identity) == "ci-deployer"


def test_unknown_identity_types_give_no_hint():
    assert _identity_name({"type": "AWSService"}) is None


def test_access_keys_are_never_part_of_the_hint():
    identity = {"type": "IAMUser", "userName": "dev-ravi", "accessKeyId": "AKIAEXAMPLE"}
    assert "AKIA" not in str(_identity_name(identity))


class _FakeCloudTrail:
    def __init__(self, events):
        self._events = events

    def lookup_events(self, **kwargs):
        return {"Events": self._events}


class _FakeSession:
    def __init__(self, events):
        self._client = _FakeCloudTrail(events)

    def client(self, name, region_name=None):
        return self._client


def _lambda(name="invoice-helper", tags=None) -> Resource:
    return Resource(
        provider=CloudProvider.AWS, account_id="123456789012", region="ap-south-1",
        service="lambda", resource_type="function",
        native_id=f"arn:aws:lambda:ap-south-1:123456789012:function:{name}",
        name=name, tags=tags or {},
    )


def _event(name, user_identity):
    return {"EventName": name, "CloudTrailEvent": json.dumps({"userIdentity": user_identity})}


def test_creator_is_found_from_the_create_event():
    session = _FakeSession([_event("CreateFunction20150331", {"type": "IAMUser", "userName": "dev-ravi"})])

    assert find_creator(session, _lambda()) == "dev-ravi"


def test_other_event_types_are_ignored():
    session = _FakeSession([_event("UpdateFunctionCode20150331v2", {"type": "IAMUser", "userName": "someone"})])

    assert find_creator(session, _lambda()) is None


def test_creator_hint_is_labelled_inferred_and_not_a_verified_owner():
    result = resolve_owner(_lambda(), creator_hint="dev-ravi")

    assert result.owner == "dev-ravi"
    assert result.source == OwnerSource.INFERRED_CREATOR