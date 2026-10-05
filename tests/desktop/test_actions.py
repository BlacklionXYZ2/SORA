"""P11.3 authorized PRESS, contact-time revalidation, and no-replay journal."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.desktop import (
    DesktopActionResult,
    DesktopActionStatus,
    DesktopNode,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopPressRequest,
    DesktopTargetRequest,
)
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import CapabilityOperation, GrantStatus
from sora.desktop import WindowsActionReply, WindowsPressRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]
STARTED = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)


def observation(
    *,
    x: int = 10,
    name: str = "Confirm fixture",
    enabled: bool = True,
) -> DesktopObservation:
    return DesktopObservation(
        status="ok",
        process_started_at=STARTED,
        nodes=(
            DesktopNode(
                node_id="button",
                process_id=123,
                window_handle=456,
                name=name,
                automation_id="fixture-confirm",
                control_type="ControlType.Button",
                runtime_id=(42, 7),
                rect=ScreenRect(x=x, y=20, width=100, height=30),
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


class RecordingActionBridge:
    def __init__(self, reply: WindowsActionReply) -> None:
        self.reply = reply
        self.requests: list[WindowsPressRequest] = []

    async def press(self, request: WindowsPressRequest) -> WindowsActionReply:
        self.requests.append(request)
        return self.reply


class HangingActionBridge:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def press(self, request: WindowsPressRequest) -> WindowsActionReply:
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
        process_id=123,
        window_handle=999,
        automation_id="fixture-confirm",
        control_type="ControlType.Button",
    )
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    await persist_operation_grant(
        runtime,
        request.observation_request.resource,
        grant_id="grant-observe-action",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    target = await runtime.acquire_desktop_target(
        request,
        grant_id="grant-observe-action",
        device_id="device-local",
    )
    return target.target_id


async def grant_press(runtime: SoraRuntime, target_id: str, grant_id: str) -> None:
    authorization = await persist_operation_grant(
        runtime,
        f"desktop.interact:{target_id}:press",
        grant_id=grant_id,
        operation=CapabilityOperation.DESKTOP_INTERACT,
    )
    await runtime.repository.save_grant(authorization.grant.model_copy(update={"max_uses": 1}))


def press_request(attempt_id: str = "press-attempt-001") -> DesktopPressRequest:
    return DesktopPressRequest(
        attempt_id=attempt_id,
        expected_name_after="Confirmed once",
    )


@pytest.mark.asyncio
async def test_verified_press_is_consumed_once_and_repeated_contact_is_deduplicated(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_press(runtime, target_id, "grant-press-once")
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    actor = RecordingActionBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_action_bridge = actor  # type: ignore[assignment]

    result = await runtime.press_desktop_target(
        target_id,
        press_request(),
        grant_id="grant-press-once",
        device_id="device-local",
    )
    assert result.status is DesktopActionStatus.COMPLETED
    assert result.effect_attempted and result.verified
    assert len(actor.requests) == 1
    assert actor.requests[0].expected_name_before == "Confirm fixture"
    assert actor.requests[0].expected_x == 10
    grant = await runtime.repository.get_grant("grant-press-once")
    assert grant is not None and grant.used_count == 1 and grant.status is GrantStatus.EXHAUSTED

    repeated = await runtime.press_desktop_target(
        target_id,
        press_request(),
        grant_id="grant-press-once",
        device_id="device-local",
    )
    assert repeated == result
    assert len(actor.requests) == 1
    with pytest.raises(ValueError, match="reused with different input"):
        await runtime.press_desktop_target(
            target_id,
            DesktopPressRequest(
                attempt_id="press-attempt-001",
                expected_name_after="Different postcondition",
            ),
            grant_id="grant-press-once",
            device_id="device-local",
        )


@pytest.mark.asyncio
async def test_expired_grant_moved_or_disabled_target_never_reaches_effect(
    runtime: SoraRuntime,
) -> None:
    expired_target = await acquire(runtime)
    await grant_press(runtime, expired_target, "grant-press-expired")
    grant = await runtime.repository.get_grant("grant-press-expired")
    assert grant is not None
    await runtime.repository.save_grant(
        grant.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    )
    actor = RecordingActionBridge(WindowsActionReply(status="unavailable"))
    runtime.windows_action_bridge = actor  # type: ignore[assignment]
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    expired = await runtime.press_desktop_target(
        expired_target,
        press_request("press-expired"),
        grant_id="grant-press-expired",
        device_id="device-local",
    )
    assert expired.status is DesktopActionStatus.FAILED
    assert expired.reason == "authorization_denied"
    assert not expired.effect_attempted and not actor.requests

    moved_target = await acquire(runtime)
    await grant_press(runtime, moved_target, "grant-press-moved")
    runtime.windows_bridge = SequenceObservationBridge(observation(x=80))  # type: ignore[assignment]
    moved = await runtime.press_desktop_target(
        moved_target,
        press_request("press-moved"),
        grant_id="grant-press-moved",
        device_id="device-local",
    )
    assert moved.status is DesktopActionStatus.FAILED
    assert moved.reason == "target_changed_at_contact"
    assert not moved.effect_attempted and not actor.requests

    disabled_target = await acquire(runtime)
    await grant_press(runtime, disabled_target, "grant-press-disabled")
    runtime.windows_bridge = SequenceObservationBridge(observation(enabled=False))  # type: ignore[assignment]
    disabled = await runtime.press_desktop_target(
        disabled_target,
        press_request("press-disabled"),
        grant_id="grant-press-disabled",
        device_id="device-local",
    )
    assert disabled.status is DesktopActionStatus.FAILED
    assert disabled.reason == "target_unavailable"
    assert not disabled.effect_attempted and not actor.requests


@pytest.mark.asyncio
async def test_cancelled_crash_window_is_unknown_and_never_replayed(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_press(runtime, target_id, "grant-press-crash")
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    actor = HangingActionBridge()
    runtime.windows_action_bridge = actor  # type: ignore[assignment]
    task = asyncio.create_task(
        runtime.press_desktop_target(
            target_id,
            press_request("press-crash"),
            grant_id="grant-press-crash",
            device_id="device-local",
        )
    )
    await actor.started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    journaled = await runtime.repository.get_desktop_action("press-crash")
    assert journaled is not None
    assert journaled.status is DesktopActionStatus.UNKNOWN_OUTCOME
    assert journaled.effect_attempted and not journaled.verified
    repeated = await runtime.press_desktop_target(
        target_id,
        press_request("press-crash"),
        grant_id="grant-press-crash",
        device_id="device-local",
    )
    assert repeated == journaled
    assert actor.calls == 1


@pytest.mark.asyncio
async def test_inflight_revocation_after_contact_observation_prevents_effect(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    authorization = await persist_operation_grant(
        runtime,
        f"desktop.interact:{target_id}:press",
        grant_id="grant-press-inflight-revoked",
        operation=CapabilityOperation.DESKTOP_INTERACT,
    )

    class RevokingObservationBridge:
        async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
            await runtime.repository.save_grant(
                authorization.grant.model_copy(update={"status": GrantStatus.REVOKED})
            )
            return observation()

    actor = RecordingActionBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_bridge = RevokingObservationBridge()  # type: ignore[assignment]
    runtime.windows_action_bridge = actor  # type: ignore[assignment]
    result = await runtime.press_desktop_target(
        target_id,
        press_request("press-inflight-revoked"),
        grant_id="grant-press-inflight-revoked",
        device_id="device-local",
    )
    assert result.status is DesktopActionStatus.FAILED
    assert result.reason == "authorization_denied"
    assert not result.effect_attempted and not actor.requests


@pytest.mark.asyncio
async def test_unverified_native_reply_and_api_route_keep_unknown_explicit(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_press(runtime, target_id, "grant-press-unknown")
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    actor = RecordingActionBridge(
        WindowsActionReply(status="unknown_outcome", effect_attempted=True)
    )
    runtime.windows_action_bridge = actor  # type: ignore[assignment]
    handler = RouteHandler(runtime)
    response = await handler.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/press",
            headers={
                "x-sora-grant-id": "grant-press-unknown",
                "x-sora-device-id": "device-local",
            },
            body=press_request("press-api-unknown").model_dump_json().encode(),
        )
    )
    assert response.status_code == 200
    payload = response.parse_json()
    assert payload["status"] == "unknown_outcome"
    assert payload["effect_attempted"] is True
    assert payload["verified"] is False


@pytest.mark.asyncio
async def test_prepared_press_keeps_grant_in_core_until_embodied_contact(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_press(runtime, target_id, "grant-prepared-press")
    queue = runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceObservationBridge(
        observation(), observation()
    )  # type: ignore[assignment]
    actor = RecordingActionBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_action_bridge = actor  # type: ignore[assignment]

    command = await runtime.prepare_desktop_press_interaction(
        target_id,
        press_request("prepared-press"),
        grant_id="grant-prepared-press",
        device_id="device-local",
    )
    assert queue.get_nowait() == command
    assert command.verb.value == "interaction_start"
    assert command.semantic_action is not None and command.semantic_action.value == "press"
    assert command.target_id == target_id
    assert "grant-prepared-press" not in command.model_dump_json()
    grant = await runtime.repository.get_grant("grant-prepared-press")
    assert grant is not None and grant.used_count == 0

    result = await runtime.contact_prepared_desktop_interaction(
        "prepared-press", device_id="device-local"
    )
    assert result.status is DesktopActionStatus.COMPLETED
    assert len(actor.requests) == 1
    grant = await runtime.repository.get_grant("grant-prepared-press")
    assert grant is not None and grant.used_count == 1
    with pytest.raises(LookupError):
        await runtime.contact_prepared_desktop_interaction(
            "prepared-press", device_id="device-local"
        )


@pytest.mark.asyncio
async def test_prepared_press_rechecks_device_and_revocation_before_effect(
    runtime: SoraRuntime,
) -> None:
    target_id = await acquire(runtime)
    await grant_press(runtime, target_id, "grant-prepared-revoked")
    runtime.register_embodiment_queue()
    runtime.windows_bridge = SequenceObservationBridge(observation())  # type: ignore[assignment]
    actor = RecordingActionBridge(
        WindowsActionReply(status="verified", effect_attempted=True, verified=True)
    )
    runtime.windows_action_bridge = actor  # type: ignore[assignment]
    await runtime.prepare_desktop_press_interaction(
        target_id,
        press_request("prepared-revoked"),
        grant_id="grant-prepared-revoked",
        device_id="device-local",
    )
    with pytest.raises(LookupError):
        await runtime.contact_prepared_desktop_interaction(
            "prepared-revoked", device_id="device-other"
        )
    grant = await runtime.repository.get_grant("grant-prepared-revoked")
    assert grant is not None
    await runtime.repository.save_grant(grant.model_copy(update={"status": GrantStatus.REVOKED}))
    with pytest.raises(PermissionError):
        await runtime.contact_prepared_desktop_interaction(
            "prepared-revoked", device_id="device-local"
        )
    assert not actor.requests


@pytest.mark.asyncio
async def test_startup_recovers_executing_attempt_as_unknown(tmp_path: Path) -> None:
    config = RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity")
    first = SoraRuntime(config, provider=DeterministicProvider())
    await first.start()
    now = datetime.now(UTC)
    pending = DesktopActionResult(
        attempt_id="press-restart",
        target_id="desktop-target-restart",
        status=DesktopActionStatus.PENDING,
        reason="reserved",
        created_at=now,
        updated_at=now,
    )
    await first.repository.reserve_desktop_action(pending, request_hash="fixture-hash")
    executing = pending.model_copy(
        update={
            "status": DesktopActionStatus.EXECUTING,
            "reason": "effect_claimed",
            "updated_at": datetime.now(UTC),
        }
    )
    await first.repository.transition_desktop_action(
        pending.attempt_id,
        expected=DesktopActionStatus.PENDING,
        result=executing,
    )
    await first.close()

    reopened = SoraRuntime(config, provider=DeterministicProvider())
    await reopened.start()
    try:
        recovered = await reopened.repository.get_desktop_action("press-restart")
        assert recovered is not None
        assert recovered.status is DesktopActionStatus.UNKNOWN_OUTCOME
        assert recovered.reason == "core_restarted_during_effect"
        assert recovered.effect_attempted and not recovered.verified
    finally:
        await reopened.close()
