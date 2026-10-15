"""Enrichment tests: owner resolution and usage summaries."""

from datetime import datetime

import pytest

from ai_discovery.enrichment.owner import resolve_owner
from ai_discovery.enrichment.usage import summarise_usage
from ai_discovery.models.enums import ActivityStatus, CloudProvider, OwnerSource
from ai_discovery.models.resource import Resource


def _make_resource(**extra) -> Resource:
    return Resource(
        provider=CloudProvider.AWS,
        account_id="123456789012",
        region="ap-south-1",
        service="lambda",
        resource_type="function",
        native_id="arn:aws:lambda:ap-south-1:123456789012:function:demo",
        name="demo",
        **extra,
    )


# ---- owner ----

def test_explicit_owner_tag_is_used():
    result = resolve_owner(_make_resource(tags={"owner": "finance-team"}))

    assert result.owner == "finance-team"
    assert result.source == OwnerSource.EXPLICIT_TAG


def test_owner_tag_key_is_case_insensitive():
    result = resolve_owner(_make_resource(tags={"Owner": "finance-team"}))

    assert result.owner == "finance-team"


def test_owner_tag_beats_creator_hint():
    result = resolve_owner(
        _make_resource(tags={"owner": "finance-team"}), creator_hint="dev-ravi"
    )

    assert result.owner == "finance-team"
    assert result.source == OwnerSource.EXPLICIT_TAG


def test_empty_owner_tag_counts_as_missing():
    result = resolve_owner(_make_resource(tags={"owner": "  "}))

    assert result.owner is None
    assert result.source == OwnerSource.UNKNOWN


def test_creator_is_labelled_inferred_not_owner():
    result = resolve_owner(_make_resource(), creator_hint="dev-ravi")

    assert result.owner == "dev-ravi"
    assert result.source == OwnerSource.INFERRED_CREATOR


def test_no_information_gives_unknown():
    result = resolve_owner(_make_resource())

    assert result.owner is None
    assert result.source == OwnerSource.UNKNOWN


# ---- usage ----

def test_calls_in_window_means_active():
    result = summarise_usage(4000)

    assert result.activity_status == ActivityStatus.ACTIVE_OBSERVED
    assert result.usage_count == 4000
    assert result.usage_window_days == 30


def test_missing_metric_is_unknown_not_zero():
    result = summarise_usage(None)

    assert result.activity_status == ActivityStatus.ACTIVITY_UNKNOWN
    assert result.usage_count is None


def test_zero_calls_with_no_history_is_no_activity():
    result = summarise_usage(0)

    assert result.activity_status == ActivityStatus.NO_ACTIVITY_OBSERVED


def test_zero_calls_after_earlier_use_is_dormant():
    result = summarise_usage(0, last_call_at=datetime(2026, 1, 5))

    assert result.activity_status == ActivityStatus.DORMANT_OBSERVED


def test_negative_count_is_rejected():
    with pytest.raises(ValueError):
        summarise_usage(-1)