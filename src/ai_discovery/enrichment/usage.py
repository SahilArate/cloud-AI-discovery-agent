"""Turns a call count over a time window into an activity status."""

from datetime import datetime

from pydantic import BaseModel

from ai_discovery.models.enums import ActivityStatus

DEFAULT_WINDOW_DAYS = 30


class UsageResult(BaseModel):
    activity_status: ActivityStatus
    usage_count: int | None
    usage_window_days: int | None


def summarise_usage(
    calls_in_window: int | None,
    window_days: int = DEFAULT_WINDOW_DAYS,
    last_call_at: datetime | None = None,
) -> UsageResult:
    """Describe activity from a metric we actually measured.

    calls_in_window is None when no metric was available (not the same as zero).
    last_call_at is the most recent call outside the window, if we know it.
    """
    if calls_in_window is None:
        return UsageResult(
            activity_status=ActivityStatus.ACTIVITY_UNKNOWN,
            usage_count=None,
            usage_window_days=None,
        )

    if calls_in_window < 0:
        raise ValueError("calls_in_window cannot be negative")

    if calls_in_window > 0:
        status = ActivityStatus.ACTIVE_OBSERVED
    elif last_call_at is not None:
        # Used before, but nothing inside the window.
        status = ActivityStatus.DORMANT_OBSERVED
    else:
        # Metrics exist and show zero, with no earlier use on record.
        status = ActivityStatus.NO_ACTIVITY_OBSERVED

    return UsageResult(
        activity_status=status,
        usage_count=calls_in_window,
        usage_window_days=window_days,
    )