"""P11.5 authorized logical TYPE, postcondition verification, and no replay."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.contracts.desktop import (
    DesktopActionStatus,
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopTargetRequest,
    DesktopTypeRequest,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import CapabilityOperation, GrantStatus
from sora.desktop import DesktopTargetError, WindowsActionReply, WindowsTypeRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]
STARTED = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def text_observation(*, x: int = 30, enabled: bool = True) -> DesktopObservation:
    return DesktopObservation(
        status="ok",
        process_started_at=STARTED,
        nodes=(
            DesktopNode(
                node_id="text",
                process_id=321,
                window_handle=654,
                name="Fixture text",
                automation_id="fixture-text",
                control_type="ControlType.Edit",
                runtime_id=(88, 9),
                rect=ScreenRect(x=x, y=100, width=240, height=30),
                focused=False,
                enabled=enabled,
                offscreen=False,
                password=False,
            ),
        ),
    )


class SequenceObservationBridge:
    def __init__(self, *results: DesktopObservation) -> None:
        self.results = list(results)

    async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
        assert self.results
        return self.results.pop(0)


class RecordingTypeBridge:
    def __init__(self, reply: WindowsActionReply) -> None:
        self.reply = reply
        self.requests: list[WindowsTypeRequest] = []

    async def type_text(self, request: WindowsTypeRequest) -> WindowsActionReply:
        self.requests.append(request)
        return self.reply


class HangingTypeBridge:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def type_text(self, request: WindowsTypeRequest) -> WindowsActionReply:
        self.calls += 1
        self.started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


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


async def acquire(runtime: SoraRuntime) -> str:
    request = DesktopTargetRequest(
        process_id=321,
        window_handle=999,
        automation_id="fixture-text",
        control_type="ControlType.Edit",
    )
    runtime.windows_bridge = SequenceObservationBridge(text_observation())  # type: ignore[assignment]
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-observe-type",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    target = await runtime.acquire_desktop_target(
        request,
        grant_id="grant-observe-type",
        device_id="device-local",
    )
    return target.target_id


async def grant_type(runtime: SoraRuntime, target_id: str, grant_id: str) -> None:
    authorization = await persist_operation_grant(
        runtime,
        f"desktop.interact:{target_id}:type",
        grant_id=grant_id,
        operation=CapabilityOperation.DESKTOP_INTERACT,
    )
    await runtime.repository.save_grant(authorization.grant.model_copy(update={"max_uses": 1}))


@pytest.mark.asyncio
async def test_verified_type_is_exact_target_scoped_deduplicated_and_text_is_not_persisted(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_type(runtime, target_id, "grant-type-once")
    runtime.windows_bridge = SequenceObservationBridge(text_observation())  # type: ignore[assignment]
    actor = RecordingTypeBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_type_bridge = actor  # type: ignore[assignment]
    sentinel = "typed-only-in-worker-P11-5"
    request = DesktopTypeRequest(attempt_id="type-once", text=sentinel)

    result = await runtime.type_desktop_target(
        target_id,
        request,
        grant_id="grant-type-once",
        device_id="device-local",
    )
    assert result.action == "type"
    assert result.status is DesktopActionStatus.COMPLETED and result.verified
    assert len(actor.requests) == 1 and actor.requests[0].text == sentinel
    grant = await runtime.repository.get_grant("grant-type-once")
    assert grant is not None and grant.used_count == 1 and grant.status is GrantStatus.EXHAUSTED
    repeated = await runtime.type_desktop_target(
        target_id,
        request,
        grant_id="grant-type-once",
        device_id="device-local",
    )
    assert repeated == result and len(actor.requests) == 1
    database_bytes = (runtime.config.root / "data" / "sora.db").read_bytes()
    assert sentinel.encode() not in database_bytes


@pytest.mark.asyncio
async def test_prepared_type_keeps_text_and_grant_out_of_unity_command(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_type(runtime, target_id, "grant-prepared-type")
    queue = runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceObservationBridge(
        text_observation(), text_observation()
    )  # type: ignore[assignment]
    actor = RecordingTypeBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_type_bridge = actor  # type: ignore[assignment]
    request = DesktopTypeRequest(attempt_id="prepared-type", text="hello from SORA")

    command = await runtime.prepare_desktop_type_interaction(
        target_id,
        request,
        grant_id="grant-prepared-type",
        device_id="device-local",
    )
    assert queue.get_nowait() == command
    serialized = command.model_dump_json()
    assert command.semantic_action is not None and command.semantic_action.value == "type"
    assert "hello from SORA" not in serialized
    assert "grant-prepared-type" not in serialized
    grant = await runtime.repository.get_grant("grant-prepared-type")
    assert grant is not None and grant.used_count == 0
    result = await runtime.contact_prepared_desktop_interaction(
        "prepared-type", device_id="device-local"
    )
    assert result.status is DesktopActionStatus.COMPLETED and result.verified
    assert actor.requests[0].text == "hello from SORA"


@pytest.mark.asyncio
async def test_moved_target_and_cancelled_effect_never_become_blind_success(
    runtime: SoraRuntime,
) -> None:
    moved_target = await acquire(runtime)
    await grant_type(runtime, moved_target, "grant-type-moved")
    actor = RecordingTypeBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_type_bridge = actor  # type: ignore[assignment]
    runtime.windows_bridge = SequenceObservationBridge(text_observation(x=90))  # type: ignore[assignment]
    moved = await runtime.type_desktop_target(
        moved_target,
        DesktopTypeRequest(attempt_id="type-moved", text="must-not-appear"),
        grant_id="grant-type-moved",
        device_id="device-local",
    )
    assert moved.status is DesktopActionStatus.FAILED
    assert moved.reason == "target_changed_at_contact"
    assert not moved.effect_attempted and not actor.requests

    cancelled_target = await acquire(runtime)
    await grant_type(runtime, cancelled_target, "grant-type-cancelled")
    runtime.windows_bridge = SequenceObservationBridge(text_observation())  # type: ignore[assignment]
    hanging = HangingTypeBridge()
    runtime.windows_type_bridge = hanging  # type: ignore[assignment]
    request = DesktopTypeRequest(attempt_id="type-cancelled", text="uncertain text")
    task = asyncio.create_task(
        runtime.type_desktop_target(
            cancelled_target,
            request,
            grant_id="grant-type-cancelled",
            device_id="device-local",
        )
    )
    await hanging.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    journaled = await runtime.repository.get_desktop_action("type-cancelled")
    assert journaled is not None
    assert journaled.status is DesktopActionStatus.UNKNOWN_OUTCOME
    assert journaled.effect_attempted and not journaled.verified
    repeated = await runtime.type_desktop_target(
        cancelled_target,
        request,
        grant_id="grant-type-cancelled",
        device_id="device-local",
    )
    assert repeated == journaled and hanging.calls == 1


@pytest.mark.asyncio
async def test_password_control_cannot_become_a_type_target(runtime: SoraRuntime) -> None:
    password_observation = DesktopObservation(
        status="ok",
        process_started_at=STARTED,
        nodes=(
            DesktopNode(
                node_id="password",
                process_id=321,
                window_handle=654,
                name="",
                automation_id="fixture-password",
                control_type="ControlType.Edit",
                runtime_id=(88, 10),
                rect=ScreenRect(x=30, y=150, width=240, height=30),
                focused=False,
                enabled=True,
                offscreen=False,
                password=True,
            ),
        ),
    )
    request = DesktopTargetRequest(
        process_id=321,
        window_handle=999,
        automation_id="fixture-password",
        control_type="ControlType.Edit",
    )
    runtime.windows_bridge = SequenceObservationBridge(password_observation)  # type: ignore[assignment]
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-observe-password",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    with pytest.raises(DesktopTargetError, match="password"):
        await runtime.acquire_desktop_target(
            request,
            grant_id="grant-observe-password",
            device_id="device-local",
        )
