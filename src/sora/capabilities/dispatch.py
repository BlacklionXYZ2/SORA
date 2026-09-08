"""Structural capability dispatch and authorization verification."""

from __future__ import annotations

from datetime import UTC, datetime

from sora.contracts.base import require_aware
from sora.contracts.models import (
    ActiveCapabilitySet,
    CapabilityDescriptor,
    CapabilityGrant,
    GrantStatus,
)


class CapabilityDeniedError(Exception):
    """Raised when an action is not authorized, expired, or absent from the active set."""


def dispatch_capability(
    action_id: str,
    active_set: ActiveCapabilitySet,
    *,
    now: datetime | None = None,
    grant: CapabilityGrant | None = None,
) -> CapabilityDescriptor:
    """Verify and retrieve capability descriptor from the active capability set."""

    current_time = now or datetime.now(UTC)
    require_aware(current_time, "now")

    if current_time >= active_set.expires_at:
        raise CapabilityDeniedError("Active capability set has expired")

    found_descriptor: CapabilityDescriptor | None = None
    for descriptor in active_set.selected_capabilities:
        if descriptor.capability_id == action_id:
            found_descriptor = descriptor
            break

    if found_descriptor is None:
        raise CapabilityDeniedError(
            f"Action '{action_id}' is not present in the active capability set"
        )

    if grant is not None:
        if grant.status is not GrantStatus.ACTIVE:
            raise CapabilityDeniedError(f"Grant '{grant.grant_id}' is inactive ({grant.status})")
        if current_time < grant.not_before:
            raise CapabilityDeniedError(f"Grant '{grant.grant_id}' is not yet valid")
        if current_time >= grant.expires_at:
            raise CapabilityDeniedError(f"Grant '{grant.grant_id}' has expired")
        if grant.max_uses is not None and grant.used_count >= grant.max_uses:
            raise CapabilityDeniedError(f"Grant '{grant.grant_id}' has exhausted permitted uses")

    return found_descriptor
