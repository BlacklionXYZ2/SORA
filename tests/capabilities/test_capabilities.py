from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sora.capabilities.dispatch import CapabilityDeniedError, dispatch_capability
from sora.capabilities.resolver import CapabilityRegistry, CapabilityResolver
from sora.contracts.models import (
    CapabilityCategory,
    CapabilityDescriptor,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityResolutionRequest,
    CapabilityScope,
    GrantStatus,
    SemanticVerb,
)


def _make_descriptor(
    cap_id: str,
    category: CapabilityCategory,
    verbs: tuple[SemanticVerb, ...] = (),
    scope: CapabilityScope = CapabilityScope.LOCAL_OWNER,
    desc: str = "test description",
) -> CapabilityDescriptor:
    return CapabilityDescriptor(
        capability_id=cap_id,
        category=category,
        verbs=verbs,
        description=desc,
        required_scope=scope,
    )


def test_capability_index_construction() -> None:
    registry = CapabilityRegistry()
    registry.register(
        _make_descriptor("cap.media.pause", CapabilityCategory.MEDIA, (SemanticVerb.PAUSE,))
    )
    registry.register(
        _make_descriptor("cap.tasks.add", CapabilityCategory.TASKS, (SemanticVerb.ADD_TASK,))
    )
    registry.register(
        _make_descriptor(
            "cap.social.post",
            CapabilityCategory.SOCIAL,
            (SemanticVerb.SEND,),
            scope=CapabilityScope.NETWORK_PUBLIC,
        )
    )

    index = registry.build_index(CapabilityScope.LOCAL_OWNER)
    categories = {entry.category for entry in index.entries}
    assert CapabilityCategory.MEDIA in categories
    assert CapabilityCategory.TASKS in categories
    assert CapabilityCategory.SOCIAL in categories

    public_index = registry.build_index(CapabilityScope.NETWORK_PUBLIC)
    public_categories = {entry.category for entry in public_index.entries}
    assert CapabilityCategory.SOCIAL in public_categories
    assert CapabilityCategory.MEDIA not in public_categories


def test_relevance_resolution_media() -> None:
    registry = CapabilityRegistry()
    registry.register(
        _make_descriptor(
            "cap.media.pause",
            CapabilityCategory.MEDIA,
            (SemanticVerb.PAUSE,),
            desc="Pause media playback",
        )
    )
    registry.register(
        _make_descriptor(
            "cap.media.play",
            CapabilityCategory.MEDIA,
            (SemanticVerb.PLAY,),
            desc="Resume media playback",
        )
    )
    registry.register(
        _make_descriptor(
            "cap.files.read",
            CapabilityCategory.FILES,
            (SemanticVerb.OPEN,),
            desc="Read a local file",
        )
    )

    resolver = CapabilityResolver(revision=1)
    request = CapabilityResolutionRequest(
        request_id="req-1",
        actor_id="user-1",
        session_id="session-1",
        scope=CapabilityScope.LOCAL_OWNER,
        intent="Could you pause this music?",
        active_window="Spotify",
    )

    now = datetime.now(UTC)
    active_set = resolver.resolve(request, registry, now=now)

    selected_ids = {c.capability_id for c in active_set.selected_capabilities}
    assert "cap.media.pause" in selected_ids
    assert "cap.files.read" not in selected_ids

    manifest_map = {m.capability_id: m.reason for m in active_set.manifest}
    assert manifest_map["cap.files.read"] == "not_relevant"
    assert manifest_map["cap.media.pause"] == "selected"


def test_large_synthetic_registry_bounded_selection() -> None:
    registry = CapabilityRegistry()
    for i in range(50):
        category = CapabilityCategory.TASKS if i < 20 else CapabilityCategory.FILES
        registry.register(
            _make_descriptor(
                f"cap.task.{i}",
                category,
                (SemanticVerb.ADD_TASK,),
                desc=f"Task action {i}",
            )
        )

    resolver = CapabilityResolver(revision=1)
    request = CapabilityResolutionRequest(
        request_id="req-budget",
        actor_id="user-1",
        session_id="session-1",
        scope=CapabilityScope.LOCAL_OWNER,
        intent="Add a new task to the board",
        max_capabilities=5,
    )

    active_set = resolver.resolve(request, registry, now=datetime.now(UTC))
    assert len(active_set.selected_capabilities) == 5

    budget_excluded = [m for m in active_set.manifest if m.reason == "budget_excluded"]
    assert len(budget_excluded) == 15  # 20 matching task capabilities minus 5 selected


def test_structural_scope_enforcement_privacy() -> None:
    registry = CapabilityRegistry()
    registry.register(
        _make_descriptor(
            "cap.local.filesystem",
            CapabilityCategory.FILES,
            (SemanticVerb.OPEN,),
            scope=CapabilityScope.LOCAL_OWNER,
        )
    )
    registry.register(
        _make_descriptor(
            "cap.social.post",
            CapabilityCategory.SOCIAL,
            (SemanticVerb.SEND,),
            scope=CapabilityScope.NETWORK_PUBLIC,
        )
    )

    resolver = CapabilityResolver(revision=1)
    request = CapabilityResolutionRequest(
        request_id="req-social",
        actor_id="network-peer",
        session_id="session-social",
        scope=CapabilityScope.NETWORK_PUBLIC,
        intent="Send a public social post and open files",
    )

    active_set = resolver.resolve(request, registry, now=datetime.now(UTC))
    selected_ids = {c.capability_id for c in active_set.selected_capabilities}
    assert "cap.social.post" in selected_ids
    assert "cap.local.filesystem" not in selected_ids

    manifest_map = {m.capability_id: m.reason for m in active_set.manifest}
    assert manifest_map["cap.local.filesystem"] == "privacy_scope_excluded"


def test_remote_guest_strictly_disabled() -> None:
    registry = CapabilityRegistry()
    registry.register(_make_descriptor("cap.test", CapabilityCategory.DESKTOP))

    resolver = CapabilityResolver(revision=1)
    request = CapabilityResolutionRequest(
        request_id="req-guest",
        actor_id="guest-1",
        session_id="session-guest",
        scope=CapabilityScope.REMOTE_GUEST,
        intent="Move around and inspect screen",
    )

    active_set = resolver.resolve(request, registry, now=datetime.now(UTC))
    assert len(active_set.selected_capabilities) == 0
    assert active_set.manifest[0].reason == "remote_guest_unavailable"


def test_dispatch_capability_authorized() -> None:
    now = datetime.now(UTC)
    cap = _make_descriptor("cap.action.allowed", CapabilityCategory.DESKTOP)
    active_set = CapabilityResolver().resolve(
        CapabilityResolutionRequest(
            request_id="req-dispatch",
            actor_id="user-1",
            session_id="session-1",
            scope=CapabilityScope.LOCAL_OWNER,
            intent="Execute desktop action",
        ),
        CapabilityRegistry(),
        now=now,
    )
    # Manually add cap to active_set for direct testing
    active_set = active_set.model_copy(update={"selected_capabilities": (cap,)})

    dispatched = dispatch_capability("cap.action.allowed", active_set, now=now)
    assert dispatched.capability_id == "cap.action.allowed"


def test_dispatch_capability_unexposed_denied() -> None:
    now = datetime.now(UTC)
    active_set = CapabilityResolver().resolve(
        CapabilityResolutionRequest(
            request_id="req-dispatch",
            actor_id="user-1",
            session_id="session-1",
            scope=CapabilityScope.LOCAL_OWNER,
            intent="nothing",
        ),
        CapabilityRegistry(),
        now=now,
    )

    with pytest.raises(CapabilityDeniedError, match="not present in the active capability set"):
        dispatch_capability("cap.guessed.action", active_set, now=now)


def test_dispatch_capability_expired_denied() -> None:
    now = datetime.now(UTC)
    cap = _make_descriptor("cap.test", CapabilityCategory.DESKTOP)
    active_set = CapabilityResolver().resolve(
        CapabilityResolutionRequest(
            request_id="req-exp",
            actor_id="user-1",
            session_id="session-1",
            scope=CapabilityScope.LOCAL_OWNER,
            intent="test",
        ),
        CapabilityRegistry(),
        now=now,
        ttl_seconds=1.0,
    )
    active_set = active_set.model_copy(update={"selected_capabilities": (cap,)})

    future_time = now + timedelta(seconds=10.0)
    with pytest.raises(CapabilityDeniedError, match="has expired"):
        dispatch_capability("cap.test", active_set, now=future_time)


def test_dispatch_capability_grant_validation() -> None:
    now = datetime.now(UTC)
    cap = _make_descriptor("cap.write", CapabilityCategory.FILES)
    active_set = CapabilityResolver().resolve(
        CapabilityResolutionRequest(
            request_id="req-grant",
            actor_id="user-1",
            session_id="session-1",
            scope=CapabilityScope.LOCAL_OWNER,
            intent="write",
        ),
        CapabilityRegistry(),
        now=now,
    )
    active_set = active_set.model_copy(update={"selected_capabilities": (cap,)})

    # Inactive grant
    grant_inactive = CapabilityGrant(
        grant_id="grant-1",
        owner_id="owner-1",
        device_id="device-1",
        operation=CapabilityOperation.PATH_WRITE,
        resource="C:/allowed/path",
        status=GrantStatus.REVOKED,
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(hours=1),
        approval_id="app-1",
    )
    with pytest.raises(CapabilityDeniedError, match="inactive"):
        dispatch_capability("cap.write", active_set, now=now, grant=grant_inactive)

    # Exhausted grant
    grant_exhausted = CapabilityGrant(
        grant_id="grant-2",
        owner_id="owner-1",
        device_id="device-1",
        operation=CapabilityOperation.PATH_WRITE,
        resource="C:/allowed/path",
        status=GrantStatus.ACTIVE,
        issued_at=now,
        not_before=now,
        expires_at=now + timedelta(hours=1),
        max_uses=1,
        used_count=1,
        approval_id="app-2",
    )
    with pytest.raises(CapabilityDeniedError, match="exhausted"):
        dispatch_capability("cap.write", active_set, now=now, grant=grant_exhausted)
