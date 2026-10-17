"""AWS collector. Read-only: it lists resources and records what it could not see."""

import boto3
from ai_discovery.collectors.usage_aws import read_invocation_count
from botocore.exceptions import BotoCoreError, ClientError

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.collectors.base import BaseCollector, CollectionResult, ScanScope
from ai_discovery.models.coverage import CollectionError, ScopeCoverage
from ai_discovery.models.enums import CloudProvider, CoverageStatus
from ai_discovery.models.resource import Resource
from ai_discovery.collectors.owner_hints_aws import find_creator


def _error_code(error: Exception) -> str:
    if isinstance(error, ClientError):
        return error.response.get("Error", {}).get("Code", "UNKNOWN_ERROR")
    return type(error).__name__


class AWSCollector(BaseCollector):
    provider = CloudProvider.AWS

    def __init__(self, session: boto3.Session | None = None) -> None:
        self._session = session or boto3.Session()
        self._catalog = load_catalog(CloudProvider.AWS)

    def collect(self, scope: ScanScope) -> CollectionResult:
        result = CollectionResult()
        service_collectors = (
            self._collect_lambda_functions,
            self._collect_sagemaker,
            self._collect_ec2_instances,
            self._collect_secret_names,
        )
        for region in scope.regions:
            for collect_service in service_collectors:
                resources, coverage = collect_service(scope.account_id, region)
                result.resources.extend(resources)
                result.coverage.append(coverage)
        return result

    def read_usage(self, resource: Resource) -> int | None:
        return read_invocation_count(self._session, resource)

    def find_creator(self, resource: Resource) -> str | None:
        return find_creator(self._session, resource)

    def _collect_lambda_functions(
        self, account_id: str, region: str
    ) -> tuple[list[Resource], ScopeCoverage]:
        client = self._session.client("lambda", region_name=region)
        resources: list[Resource] = []
        errors: list[CollectionError] = []
        inspected = 0

        try:
            pages = client.get_paginator("list_functions").paginate()
            for page in pages:
                for function in page["Functions"]:
                    resource, tags_ok = self._build_lambda_resource(
                        client, function, account_id, region, errors
                    )
                    resources.append(resource)
                    if tags_ok:
                        inspected += 1
        except (ClientError, BotoCoreError) as error:
            errors.append(CollectionError(code=_error_code(error), operation="lambda:ListFunctions"))

        coverage = ScopeCoverage(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="lambda",
            status=self._status_for(len(resources), inspected, errors),
            resources_discovered=len(resources),
            resources_inspected=inspected,
            errors=errors,
        )
        return resources, coverage

    def _build_lambda_resource(
        self, client, function: dict, account_id: str, region: str, errors: list[CollectionError]
    ) -> tuple[Resource, bool]:
        arn = function["FunctionArn"]

        tags: dict[str, str] = {}
        tags_ok = True
        try:
            tags = client.list_tags(Resource=arn).get("Tags", {})
        except (ClientError, BotoCoreError) as error:
            tags_ok = False
            errors.append(CollectionError(code=_error_code(error), operation="lambda:ListTags"))

        # AWS returns env var values here. Keep the names and drop the values immediately.
        env_var_names = sorted(function.get("Environment", {}).get("Variables", {}).keys())

        resource = Resource(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="lambda",
            resource_type="function",
            native_id=arn,
            name=function["FunctionName"],
            tags=tags,
            env_var_names=env_var_names,
            config={
                "runtime": function.get("Runtime"),
                "handler": function.get("Handler"),
                "layers": [layer["Arn"] for layer in function.get("Layers", [])],
                "description": function.get("Description", ""),
                "last_modified": function.get("LastModified"),
            },
        )
        return resource, tags_ok

    def _collect_sagemaker(
        self, account_id: str, region: str
    ) -> tuple[list[Resource], ScopeCoverage]:
        client = self._session.client("sagemaker", region_name=region)
        resources: list[Resource] = []
        errors: list[CollectionError] = []
        inspected = 0

        # (paginator, key in the response, resource type, name field, ARN field, operation)
        listings = [
            ("list_endpoints", "Endpoints", "endpoint",
             "EndpointName", "EndpointArn", "sagemaker:ListEndpoints"),
            ("list_notebook_instances", "NotebookInstances", "notebook_instance",
             "NotebookInstanceName", "NotebookInstanceArn", "sagemaker:ListNotebookInstances"),
        ]

        # One listing failing must not hide the other, so each gets its own try block.
        for paginator_name, response_key, resource_type, name_field, arn_field, operation in listings:
            try:
                for page in client.get_paginator(paginator_name).paginate():
                    for item in page[response_key]:
                        resource, tags_ok = self._build_sagemaker_resource(
                            client, item, resource_type, name_field, arn_field,
                            account_id, region, errors,
                        )
                        resources.append(resource)
                        if tags_ok:
                            inspected += 1
            except (ClientError, BotoCoreError) as error:
                errors.append(CollectionError(code=_error_code(error), operation=operation))

        coverage = ScopeCoverage(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="sagemaker",
            status=self._status_for(len(resources), inspected, errors),
            resources_discovered=len(resources),
            resources_inspected=inspected,
            errors=errors,
        )
        return resources, coverage

    def _build_sagemaker_resource(
        self, client, item: dict, resource_type: str, name_field: str, arn_field: str,
        account_id: str, region: str, errors: list[CollectionError],
    ) -> tuple[Resource, bool]:
        arn = item[arn_field]

        tags: dict[str, str] = {}
        tags_ok = True
        try:
            tag_list = client.list_tags(ResourceArn=arn).get("Tags", [])
            tags = {tag["Key"]: tag["Value"] for tag in tag_list}
        except (ClientError, BotoCoreError) as error:
            tags_ok = False
            errors.append(CollectionError(code=_error_code(error), operation="sagemaker:ListTags"))

        resource = Resource(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="sagemaker",
            resource_type=resource_type,
            native_id=arn,
            name=item[name_field],
            tags=tags,
            created_at=item.get("CreationTime"),
            config={
                "status": item.get("EndpointStatus") or item.get("NotebookInstanceStatus"),
                "instance_type": item.get("InstanceType"),
                "last_modified": str(item.get("LastModifiedTime", "")),
            },
        )
        return resource, tags_ok

    @staticmethod
    def _tags_to_dict(tag_list: list[dict]) -> dict[str, str]:
        return {tag["Key"]: tag["Value"] for tag in tag_list}

    def _collect_ec2_instances(
        self, account_id: str, region: str
    ) -> tuple[list[Resource], ScopeCoverage]:
        client = self._session.client("ec2", region_name=region)
        resources: list[Resource] = []
        errors: list[CollectionError] = []

        try:
            for page in client.get_paginator("describe_instances").paginate():
                for reservation in page["Reservations"]:
                    for instance in reservation["Instances"]:
                        resources.append(self._build_ec2_resource(instance, account_id, region))
        except (ClientError, BotoCoreError) as error:
            errors.append(CollectionError(code=_error_code(error), operation="ec2:DescribeInstances"))

        # Tags come back in the listing itself, so everything listed was fully inspected.
        coverage = ScopeCoverage(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="ec2",
            status=self._status_for(len(resources), len(resources), errors),
            resources_discovered=len(resources),
            resources_inspected=len(resources),
            errors=errors,
        )
        return resources, coverage

    def _build_ec2_resource(self, instance: dict, account_id: str, region: str) -> Resource:
        instance_id = instance["InstanceId"]
        tags = self._tags_to_dict(instance.get("Tags", []))

        return Resource(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="ec2",
            resource_type="instance",
            native_id=f"arn:aws:ec2:{region}:{account_id}:instance/{instance_id}",
            name=tags.get("Name", instance_id),
            tags=tags,
            created_at=instance.get("LaunchTime"),
            config={
                "instance_type": instance.get("InstanceType"),
                "state": instance.get("State", {}).get("Name"),
                "image_id": instance.get("ImageId"),
            },
        )

    def _collect_secret_names(
        self, account_id: str, region: str
    ) -> tuple[list[Resource], ScopeCoverage]:
        client = self._session.client("secretsmanager", region_name=region)
        resources: list[Resource] = []
        errors: list[CollectionError] = []

        # Only ListSecrets is ever called. GetSecretValue is deliberately never used,
        # so the read-only role does not even need permission to read a secret's value.
        try:
            for page in client.get_paginator("list_secrets").paginate():
                for secret in page["SecretList"]:
                    resources.append(self._build_secret_resource(secret, account_id, region))
        except (ClientError, BotoCoreError) as error:
            errors.append(CollectionError(code=_error_code(error), operation="secretsmanager:ListSecrets"))

        coverage = ScopeCoverage(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="secretsmanager",
            status=self._status_for(len(resources), len(resources), errors),
            resources_discovered=len(resources),
            resources_inspected=len(resources),
            errors=errors,
        )
        return resources, coverage

    def _build_secret_resource(self, secret: dict, account_id: str, region: str) -> Resource:
        return Resource(
            provider=CloudProvider.AWS,
            account_id=account_id,
            region=region,
            service="secretsmanager",
            resource_type="secret",
            native_id=secret["ARN"],
            name=secret["Name"],
            tags=self._tags_to_dict(secret.get("Tags", [])),
            created_at=secret.get("CreatedDate"),
            config={"description": secret.get("Description", "")},
        )

    @staticmethod
    def _status_for(discovered: int, inspected: int, errors: list[CollectionError]) -> CoverageStatus:
        if not errors:
            return CoverageStatus.COMPLETE
        if discovered == 0:
            return CoverageStatus.FAILED
        return CoverageStatus.PARTIAL