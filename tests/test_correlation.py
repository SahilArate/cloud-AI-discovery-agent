"""Secret correlation tests: plain Resource objects, no cloud and no database."""

import pytest

from ai_discovery.catalog.loader import load_catalog
from ai_discovery.detection.correlate import link_secrets
from ai_discovery.models.enums import CloudProvider
from ai_discovery.models.resource import Resource


@pytest.fixture(scope="module")
def catalog():
    return load_catalog(CloudProvider.AWS)


def _resource(name, resource_type="function", region="ap-south-1", env=None,
              provider=CloudProvider.AWS, account="123456789012") -> Resource:
    return Resource(
        provider=provider,
        account_id=account,
        region=region,
        service="secretsmanager" if resource_type == "secret" else "lambda",
        resource_type=resource_type,
        native_id=f"id/{resource_type}/{name}/{region}",
        name=name,
        env_var_names=env or [],
    )


def test_secret_is_linked_to_a_consumer_with_the_same_env_var_name(catalog):
    secret = _resource("OPENAI_API_KEY", "secret")
    consumer = _resource("invoice-helper", env=["OPENAI_API_KEY"])

    extra, absorbed = link_secrets([secret, consumer], catalog)

    assert absorbed == {secret.asset_key}
    assert "link is by name only" in extra[consumer.asset_key][0].detail


def test_secret_in_another_region_is_not_linked(catalog):
    secret = _resource("OPENAI_API_KEY", "secret", region="us-east-1")
    consumer = _resource("invoice-helper", env=["OPENAI_API_KEY"])

    extra, absorbed = link_secrets([secret, consumer], catalog)

    assert extra == {} and absorbed == set()


def test_global_secret_links_to_a_consumer_in_any_region(catalog):
    secret = _resource("OPENAI_API_KEY", "secret", region="global")
    consumer = _resource("invoice-helper", region="asia-south1", env=["OPENAI_API_KEY"])

    _, absorbed = link_secrets([secret, consumer], catalog)

    assert absorbed == {secret.asset_key}


def test_dashed_key_vault_name_matches_an_underscored_setting(catalog):
    secret = _resource("OPENAI-API-KEY", "secret")
    consumer = _resource("hr-assistant", env=["OPENAI_API_KEY"])

    _, absorbed = link_secrets([secret, consumer], catalog)

    assert absorbed == {secret.asset_key}


def test_secret_nobody_uses_stays_a_standalone_asset(catalog):
    secret = _resource("OPENAI_API_KEY", "secret")
    bystander = _resource("report-builder", env=["LOG_LEVEL"])

    extra, absorbed = link_secrets([secret, bystander], catalog)

    assert extra == {} and absorbed == set()