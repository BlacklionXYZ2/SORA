"""Social identity projection and external observation boundary."""

from __future__ import annotations

from sora.context.compiler import ContextItem, ContextSource
from sora.contracts.models import NetworkProfileProjection, SocialEventRecord
from sora.identity.loader import IdentityBundle


def project_public_profile(
    identity: IdentityBundle,
    *,
    network: str = "nekoverse",
    handle: str = "sora_spatial",
) -> NetworkProfileProjection:
    """Project public identity fields without leaking private files or system details."""
    persona_text = identity.files.get("persona.md", "SORA agent")
    # First line as bio
    bio = persona_text.splitlines()[0] if persona_text else "SORA persistent companion"

    return NetworkProfileProjection(
        profile_id=f"profile-{network}-{handle}",
        network=network,
        handle=handle,
        display_name="SORA",
        bio=bio[:160],
        public_interests=("spatial computing", "recursive antics", "companionship"),
    )


def ingest_social_event(event: SocialEventRecord) -> ContextItem:
    """Convert external social event into an untrusted observation ContextItem."""
    # Social events are untrusted external observations, never authoritative facts.
    return ContextItem(
        source_id=f"social-{event.event_id}",
        source=ContextSource.MEMORY,
        owner_id=event.network,
        project_id=None,
        content=(
            f"[SOCIAL_EVENT:{event.network}] From {event.actor} "
            f"({event.trust_classification}): {event.content}"
        ),
        sensitivity="public",
        valid_until=None,
    )


def validate_outbound_social_payload(
    payload: str,
    forbidden_sentinels: tuple[str, ...],
) -> bool:
    """Validate that outbound social payloads do not contain private sentinels."""
    payload_lower = payload.lower()
    for sentinel in forbidden_sentinels:
        if sentinel.lower() in payload_lower:
            raise ValueError(
                f"Outbound social payload contains forbidden private sentinel: {sentinel}"
            )
    return True
