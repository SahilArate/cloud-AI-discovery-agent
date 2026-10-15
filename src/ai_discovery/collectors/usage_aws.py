"""Reads invocation counts from CloudWatch. Read-only, one metric query per resource."""

from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ai_discovery.models.resource import Resource

# (service, resource_type) -> (namespace, metric name, dimension name, dimension value source)
_METRICS = {
    ("lambda", "function"): ("AWS/Lambda", "Invocations", "FunctionName", "name"),
    ("sagemaker", "endpoint"): ("AWS/SageMaker", "Invocations", "EndpointName", "name"),
}


def supports_usage(resource: Resource) -> bool:
    return (resource.service, resource.resource_type) in _METRICS


def read_invocation_count(
    session: boto3.Session, resource: Resource, window_days: int = 30
) -> int | None:
    """Total invocations in the window, or None if we could not measure it.

    None means "unknown" (unsupported resource or a failed call), which is
    different from 0, meaning "measured and nothing happened".
    """
    if not supports_usage(resource):
        return None

    namespace, metric, dimension_name, _ = _METRICS[(resource.service, resource.resource_type)]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=window_days)

    try:
        client = session.client("cloudwatch", region_name=resource.region)
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=[{"Name": dimension_name, "Value": resource.name}],
            StartTime=start,
            EndTime=end,
            Period=window_days * 86400,
            Statistics=["Sum"],
        )
    except (ClientError, BotoCoreError):
        return None

    points = response.get("Datapoints", [])
    # No datapoints on a resource CloudWatch knows about means zero invocations.
    return int(sum(point["Sum"] for point in points))