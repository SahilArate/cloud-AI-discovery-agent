"""Works out who owns a resource, and says how we know."""

from pydantic import BaseModel

from ai_discovery.models.enums import OwnerSource
from ai_discovery.models.resource import Resource

# Tag keys that mean "this is the owner", checked in this order, case-insensitively.
OWNER_TAG_KEYS = ("owner", "team", "business-owner", "cost-center-owner")


class OwnerResult(BaseModel):
    owner: str | None
    source: OwnerSource


def resolve_owner(resource: Resource, creator_hint: str | None = None) -> OwnerResult:
    """Pick an owner using explicit tags first.

    creator_hint is who created the resource, for example from an audit log. It is only
    used when no tag exists, and it is labelled as inferred because people change teams.
    """
    lowered_tags = {key.lower(): value.strip() for key, value in resource.tags.items()}

    for tag_key in OWNER_TAG_KEYS:
        value = lowered_tags.get(tag_key)
        if value:  # an empty tag value is the same as no tag
            return OwnerResult(owner=value, source=OwnerSource.EXPLICIT_TAG)

    if creator_hint:
        return OwnerResult(owner=creator_hint, source=OwnerSource.INFERRED_CREATOR)

    return OwnerResult(owner=None, source=OwnerSource.UNKNOWN)