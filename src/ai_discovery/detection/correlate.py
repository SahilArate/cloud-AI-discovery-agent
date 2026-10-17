"""Links AI-named secrets to the resources that appear to use them. Name match only."""

from collections import defaultdict

from ai_discovery.catalog.loader import Catalog
from ai_discovery.models.enums import EvidenceStrength, EvidenceType
from ai_discovery.models.evidence import Evidence
from ai_discovery.models.resource import Resource

GLOBAL_REGION = "global"


def _normalise(name: str) -> str:
    # Key Vault forbids underscores, so OPENAI-API-KEY and OPENAI_API_KEY are the same lead.
    return name.upper().replace("-", "_")


def _same_scope(secret: Resource, consumer: Resource) -> bool:
    if secret.provider != consumer.provider or secret.account_id != consumer.account_id:
        return False
    return secret.region == consumer.region or secret.region == GLOBAL_REGION


def link_secrets(
    resources: list[Resource], catalog: Catalog
) -> tuple[dict[str, list[Evidence]], set[str]]:
    """Returns (extra evidence keyed by consumer asset_key, asset_keys of absorbed secrets)."""
    known_names = {_normalise(name) for name in catalog.signals.ai_secret_name_patterns}
    secrets = [
        r for r in resources if r.resource_type == "secret" and _normalise(r.name) in known_names
    ]
    consumers = [r for r in resources if r.resource_type != "secret"]

    extra: dict[str, list[Evidence]] = defaultdict(list)
    absorbed: set[str] = set()

    for secret in secrets:
        secret_name = _normalise(secret.name)
        for consumer in consumers:
            uses_name = secret_name in {_normalise(n) for n in consumer.env_var_names}
            if uses_name and _same_scope(secret, consumer):
                extra[consumer.asset_key].append(
                    Evidence(
                        asset_key=consumer.asset_key,
                        evidence_type=EvidenceType.AI_SECRET_NAME,
                        strength=EvidenceStrength.SUPPORTING,
                        source="secret_correlation",
                        detail=(
                            f"secret {secret.name} exists in the same account and scope; "
                            "link is by name only"
                        ),
                    )
                )
                absorbed.add(secret.asset_key)

    return dict(extra), absorbed