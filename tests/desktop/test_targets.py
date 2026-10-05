"""P10.2 volatile targets, identity freshness, and Level 0-2 authority separation."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.desktop import (
    DesktopAuthority,
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopPresentationVerb,
    DesktopTarget,
    DesktopTargetRequest,
)
from sora.contracts.embodiment import EmbodimentVerb, MonitorDescriptor, ScreenRect
from sora.contracts.models import CapabilityOperation, GrantStatus
from sora.desktop import DesktopTargetError, DesktopTargetRegistry, WindowsObservationBridge
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError

ROOT = Path(__file__).resolve().parents[2]
STARTED = datetime(2026, 9, 10, 8, 0, tzinfo=UTC)


def node(
    *,
    x: int = 10,
    automation_id: str = "fixture-confirm",
    runtime_id: tuple[int, ...] = (42, 7),
) -> DesktopNode:
    return DesktopNode(
        node_id=f"node-{x}",
        process_id=123,
        window_handle=456,
        name="Confirm fixture",
        automation_id=automation_id,
        control_type="ControlType.Button",
        runtime_id=runtime_id,
        rect=ScreenRect(x=x, y=20, width=100, height=30),
        focused=False,
        enabled=True,
        offscreen=False,
        password=False,
    )


def observation(*nodes: DesktopNode, started: datetime = STARTED) -> DesktopObservation:
    return DesktopObservation(status="ok", nodes=nodes, process_started_at=started)


class SequenceBridge(WindowsObservationBridge):
    def __init__(self, *results: DesktopObservation) -> None:
        super().__init__(Path("unused"))
        self.results = list(results)

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        assert self.results
        return self.results.pop(0)


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    result = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await result.start()
    try:
        yield result
    finally:
        await result.close()


def target_request(**updates: object) -> DesktopTargetRequest:
    values: dict[str, object] = {
        "process_id": 123,
        "window_handle": 999,
        "automation_id": "fixture-confirm",
        "control_type": "ControlType.Button",
    }
    values.update(updates)
    return DesktopTargetRequest.model_validate(values)


async def acquire(runtime: SoraRuntime, bridge: SequenceBridge) -> DesktopTarget:
    runtime.windows_bridge = bridge
    request = target_request()
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-observe-target",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    return await runtime.acquire_desktop_target(
        request,
        grant_id="grant-observe-target",
        device_id="device-local",
    )


@pytest.mark.asyncio
async def test_target_revalidation_moves_and_authority_levels_are_distinct(
    runtime: SoraRuntime,
) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    runtime.windows_bridge = SequenceBridge(observation(node(x=50)))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-present",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    moved = await runtime.revalidate_desktop_target(
        target.target_id,
        authority=DesktopAuthority.PRESENT,
        grant_id="grant-present",
        device_id="device-local",
    )
    assert moved.rect.x == 50
    assert moved.last_validated_at >= target.last_validated_at

    # A Level 1 presentation grant cannot be relabelled as Level 2 navigation.
    with pytest.raises(OperationAuthorizationError):
        await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.NAVIGATE,
            grant_id="grant-present",
            device_id="device-local",
        )

    runtime.windows_bridge = SequenceBridge(observation(node(x=75)))
    await persist_operation_grant(
        runtime,
        f"desktop.navigate:{target.target_id}",
        grant_id="grant-navigate",
        operation=CapabilityOperation.DESKTOP_NAVIGATE,
    )
    navigable = await runtime.revalidate_desktop_target(
        target.target_id,
        authority=DesktopAuthority.NAVIGATE,
        grant_id="grant-navigate",
        device_id="device-local",
    )
    assert navigable.rect.x == 75


@pytest.mark.asyncio
async def test_closed_reused_ambiguous_and_cross_device_targets_fail_closed(
    runtime: SoraRuntime,
) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    with pytest.raises(DesktopTargetError, match="not found"):
        runtime.desktop_targets.get(
            target.target_id,
            owner_id=runtime.config.owner_id,
            device_id="device-other",
            project_id=runtime.config.project_id,
        )

    await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-present-identity",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    runtime.windows_bridge = SequenceBridge(
        observation(node(), started=STARTED + timedelta(seconds=1))
    )
    with pytest.raises(DesktopTargetError) as changed:
        await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-identity",
            device_id="device-local",
        )
    assert changed.value.code == "unavailable"

    second = await acquire(runtime, SequenceBridge(observation(node())))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{second.target_id}",
        grant_id="grant-present-ambiguous",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    runtime.windows_bridge = SequenceBridge(observation(node(), node(x=11)))
    with pytest.raises(DesktopTargetError) as ambiguous:
        await runtime.revalidate_desktop_target(
            second.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-ambiguous",
            device_id="device-local",
        )
    assert ambiguous.value.code == "ambiguous"

    third = await acquire(runtime, SequenceBridge(observation(node())))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{third.target_id}",
        grant_id="grant-present-closed",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    runtime.windows_bridge = SequenceBridge(DesktopObservation(status="unavailable"))
    with pytest.raises(DesktopTargetError) as closed:
        await runtime.revalidate_desktop_target(
            third.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-closed",
            device_id="device-local",
        )
    assert closed.value.code == "unavailable"


@pytest.mark.asyncio
async def test_revocation_and_layout_change_invalidate_target(runtime: SoraRuntime) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    auth = await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-present-revoked",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    await runtime.repository.save_grant(
        auth.grant.model_copy(update={"status": GrantStatus.REVOKED})
    )
    with pytest.raises(OperationAuthorizationError):
        await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-revoked",
            device_id="device-local",
        )

    rect = ScreenRect(x=0, y=0, width=640, height=480)
    runtime.update_embodiment_topology(
        (MonitorDescriptor(id="changed", primary=True, rect=rect),), rect
    )
    with pytest.raises(DesktopTargetError) as stale:
        await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-revoked",
            device_id="device-local",
        )
    assert stale.value.code == "stale_layout"


@pytest.mark.asyncio
async def test_inflight_revocation_discards_revalidation(runtime: SoraRuntime) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    auth = await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-present-inflight",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )

    class RevokingBridge(SequenceBridge):
        async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
            await runtime.repository.save_grant(
                auth.grant.model_copy(update={"status": GrantStatus.REVOKED})
            )
            return observation(node(x=90))

    runtime.windows_bridge = RevokingBridge()
    with pytest.raises(OperationAuthorizationError):
        await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-present-inflight",
            device_id="device-local",
        )
    with pytest.raises(DesktopTargetError) as revoked:
        runtime.desktop_targets.get(
            target.target_id,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
        )
    assert revoked.value.code == "revoked"


def test_target_expiry_capacity_and_ambiguous_acquisition() -> None:
    now = [STARTED]
    registry = DesktopTargetRegistry(max_targets=1, clock=lambda: now[0])
    request = target_request(ttl_seconds=1)
    observed = observation(node()).model_copy(update={"topology_revision": 1})
    target = registry.issue(
        request,
        observed,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
    )
    now[0] += timedelta(seconds=1)
    with pytest.raises(DesktopTargetError) as expired:
        registry.get(
            target.target_id,
            owner_id="owner-local",
            device_id="device-local",
            project_id="project-sora",
        )
    assert expired.value.code == "expired"

    with pytest.raises(DesktopTargetError) as ambiguous:
        registry.issue(
            request,
            observation(node(), node(x=11)).model_copy(update={"topology_revision": 1}),
            owner_id="owner-local",
            device_id="device-local",
            project_id="project-sora",
        )
    assert ambiguous.value.code == "ambiguous"


@pytest.mark.asyncio
async def test_target_api_acquires_and_revalidates(runtime: SoraRuntime) -> None:
    request = target_request()
    runtime.windows_bridge = SequenceBridge(observation(node()))
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-api-observe-target",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    handler = RouteHandler(runtime)
    acquired = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/targets",
            headers={
                "x-sora-grant-id": "grant-api-observe-target",
                "x-sora-device-id": "device-local",
            },
            body=request.model_dump_json().encode(),
        )
    )
    assert acquired.status_code == 201
    target_id = acquired.parse_json()["target_id"]

    runtime.windows_bridge = SequenceBridge(observation(node(x=80)))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{target_id}",
        grant_id="grant-api-present",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    revalidated = await handler.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/revalidate",
            headers={
                "x-sora-grant-id": "grant-api-present",
                "x-sora-device-id": "device-local",
            },
            body=b'{"authority":"present"}',
        )
    )
    assert revalidated.status_code == 200
    assert revalidated.parse_json()["rect"]["x"] == 80

    queue = runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceBridge(observation(node(x=90)))
    presented = await handler.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/present",
            headers={
                "x-sora-grant-id": "grant-api-present",
                "x-sora-device-id": "device-local",
            },
            body=b'{"verb":"point"}',
        )
    )
    assert presented.status_code == 200
    assert presented.parse_json()["command"]["target_id"] == target_id
    assert queue.get_nowait().verb is EmbodimentVerb.SHOW_MARKER


@pytest.mark.asyncio
async def test_walk_turn_point_retarget_and_disappearance_never_invoke_ui(
    runtime: SoraRuntime,
) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    queue = runtime.register_embodiment_queue()
    auth = await persist_operation_grant(
        runtime,
        f"desktop.present:{target.target_id}",
        grant_id="grant-present-actions",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    expected = (
        (DesktopPresentationVerb.WALK, EmbodimentVerb.MOVE_TO, 20),
        (DesktopPresentationVerb.TURN, EmbodimentVerb.LOOK_AT, 30),
        (DesktopPresentationVerb.POINT, EmbodimentVerb.SHOW_MARKER, 40),
    )
    for presentation, embodiment, x in expected:
        runtime.windows_bridge = SequenceBridge(observation(node(x=x)))
        command = await runtime.present_desktop_target(
            target.target_id,
            verb=presentation,
            grant_id="grant-present-actions",
            device_id="device-local",
        )
        queued = queue.get_nowait()
        assert queued == command
        assert queued.verb is embodiment
        assert queued.target_point is not None and queued.target_point.x == x + 50
        assert await runtime.validate_embodiment_delivery(queued)

    await runtime.repository.save_grant(
        auth.grant.model_copy(update={"status": GrantStatus.REVOKED})
    )
    assert not await runtime.validate_embodiment_delivery(command)

    other = await acquire(runtime, SequenceBridge(observation(node())))
    await persist_operation_grant(
        runtime,
        f"desktop.present:{other.target_id}",
        grant_id="grant-present-disappeared",
        operation=CapabilityOperation.DESKTOP_PRESENT,
    )
    runtime.windows_bridge = SequenceBridge(DesktopObservation(status="unavailable"))
    with pytest.raises(DesktopTargetError) as disappeared:
        await runtime.present_desktop_target(
            other.target_id,
            verb=DesktopPresentationVerb.POINT,
            grant_id="grant-present-disappeared",
            device_id="device-local",
        )
    assert disappeared.value.code == "unavailable"
    assert queue.empty()


@pytest.mark.asyncio
async def test_navigation_grant_cannot_queue_presentation(runtime: SoraRuntime) -> None:
    target = await acquire(runtime, SequenceBridge(observation(node())))
    queue = runtime.register_embodiment_queue()
    await persist_operation_grant(
        runtime,
        f"desktop.navigate:{target.target_id}",
        grant_id="grant-navigation-only",
        operation=CapabilityOperation.DESKTOP_NAVIGATE,
    )
    runtime.windows_bridge = SequenceBridge(observation(node(x=50)))
    with pytest.raises(OperationAuthorizationError):
        await runtime.present_desktop_target(
            target.target_id,
            verb=DesktopPresentationVerb.POINT,
            grant_id="grant-navigation-only",
            device_id="device-local",
        )
    assert queue.empty()
