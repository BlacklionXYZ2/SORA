"""P13.1 desktop event subscription, invalidation, and storm-bound acceptance."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.attention import CursorSample, CursorSampleBatch, DesktopEventAttentionPolicy
from sora.contracts.desktop import DesktopNode, DesktopObservation, DesktopTargetRequest
from sora.contracts.desktop_events import (
    DesktopAttentionHint,
    DesktopEvent,
    DesktopEventBatch,
    DesktopEventDisposition,
    DesktopEventKind,
)
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.models import AttentionTarget, CapabilityOperation, GrantStatus, TaskStatus
from sora.desktop.events import WindowsDesktopEventSource
from sora.desktop.targets import DesktopTargetError
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


class FakeDesktopEventSource:
    def __init__(self) -> None:
        self.callback: Callable[[DesktopEvent], None] | None = None
        self.running = False

    def start(
        self,
        callback: Callable[[DesktopEvent], None],
        *,
        device_id: str,
        topology_revision: Callable[[], int],
    ) -> None:
        assert device_id == "device-local"
        assert topology_revision() >= 1
        self.callback = callback
        self.running = True

    def stop(self) -> None:
        self.running = False

    def emit(self, event: DesktopEvent) -> None:
        assert self.callback is not None
        self.callback(event)


def desktop_event(
    event_id: str,
    kind: DesktopEventKind,
    occurred_at: datetime,
    *,
    window_handle: int = 100,
    topology_revision: int = 2,
) -> DesktopEvent:
    return DesktopEvent(
        event_id=event_id,
        kind=kind,
        occurred_at=occurred_at,
        topology_revision=topology_revision,
        process_id=200,
        window_handle=window_handle,
    )


def monitor() -> MonitorDescriptor:
    return MonitorDescriptor(
        id="monitor-primary",
        primary=True,
        rect=ScreenRect(x=0, y=0, width=1920, height=1080),
        work_area=ScreenRect(x=0, y=0, width=1920, height=1040),
    )


@pytest_asyncio.fixture
async def event_runtime(
    tmp_path: Path,
) -> AsyncIterator[tuple[SoraRuntime, FakeDesktopEventSource]]:
    source = FakeDesktopEventSource()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        desktop_event_source=source,
    )
    await runtime.start()
    runtime.update_embodiment_topology((monitor(),))
    try:
        yield runtime, source
    finally:
        await runtime.close()


def test_event_contract_forbids_content_and_policy_collapses_bursts() -> None:
    now = datetime.now(UTC)
    policy = DesktopEventAttentionPolicy()
    foreground = desktop_event("event-foreground", DesktopEventKind.FOREGROUND_CHANGED, now)
    repeated = desktop_event(
        "event-foreground-repeat",
        DesktopEventKind.FOREGROUND_CHANGED,
        now + timedelta(milliseconds=100),
    )
    dialog = desktop_event(
        "event-dialog",
        DesktopEventKind.DIALOG_OPENED,
        now + timedelta(milliseconds=150),
    )

    first = policy.classify(foreground, device_id="device-local", now=now)
    debounced = policy.classify(
        repeated, device_id="device-local", now=now + timedelta(milliseconds=100)
    )
    important = policy.classify(
        dialog, device_id="device-local", now=now + timedelta(milliseconds=150)
    )
    duplicate = policy.classify(
        dialog, device_id="device-local", now=now + timedelta(milliseconds=200)
    )
    result = policy.result((first, debounced, important, duplicate))

    assert first.context_invalidated
    assert debounced.disposition is DesktopEventDisposition.DEBOUNCED
    assert important.attention_hint is DesktopAttentionHint.IMPORTANT
    assert not important.context_invalidated
    assert duplicate.disposition is DesktopEventDisposition.DEDUPLICATED
    assert result.accepted_count == 2
    assert result.debounced_count == 1
    assert result.deduplicated_count == 1
    assert result.context_invalidation_count == 1
    assert result.inference_requests == result.speech_requests == 0
    assert "title" not in DesktopEvent.model_fields
    assert "text" not in DesktopEvent.model_fields
    assert "pixels" not in DesktopEvent.model_fields
    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        DesktopEvent.model_validate(
            {
                **foreground.model_dump(),
                "window_title": "private-title-must-not-enter-event-envelope",
            }
        )


@pytest.mark.asyncio
async def test_runtime_event_invalidates_volatile_context_and_matching_target(
    event_runtime: tuple[SoraRuntime, FakeDesktopEventSource],
) -> None:
    runtime, _ = event_runtime
    now = datetime.now(UTC)
    runtime.attention_tracker.append_cursor_batch(
        CursorSampleBatch(
            samples=(
                CursorSample(
                    timestamp=now,
                    x=200,
                    y=300,
                    topology_revision=2,
                    target_element="private-target-not-an-event",
                ),
            )
        )
    )
    reference = runtime.reference_resolver.remember_attention(
        AttentionTarget(
            target_id="attention-before-event",
            source="hover",
            created_at=now,
            expires_at=now + timedelta(seconds=5),
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
            ui_element="private-target-not-an-event",
            screen_rect=(200, 300, 10, 10),
            topology_revision=2,
            provenance="volatile_local_input",
        )
    )
    target = runtime.desktop_targets.issue(
        DesktopTargetRequest(
            process_id=200,
            window_handle=100,
            runtime_id=(1, 2),
            control_type="ControlType.Button",
        ),
        DesktopObservation(
            status="ok",
            topology_revision=2,
            process_started_at=now - timedelta(minutes=1),
            nodes=(
                DesktopNode(
                    node_id="node-1",
                    process_id=200,
                    window_handle=100,
                    name="Fixture",
                    automation_id="fixture",
                    control_type="ControlType.Button",
                    runtime_id=(1, 2),
                    rect=ScreenRect(x=100, y=100, width=40, height=20),
                    focused=True,
                    enabled=True,
                    offscreen=False,
                    password=False,
                ),
            ),
        ),
        owner_id=runtime.config.owner_id,
        device_id="device-local",
        project_id=runtime.config.project_id,
    )
    await persist_operation_grant(
        runtime,
        "desktop.observe:events",
        grant_id="grant-events",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    result = await runtime.ingest_desktop_events(
        DesktopEventBatch(
            events=(
                desktop_event("foreground-change", DesktopEventKind.FOREGROUND_CHANGED, now),
                desktop_event(
                    "closed-window",
                    DesktopEventKind.WINDOW_CLOSED,
                    now + timedelta(milliseconds=600),
                ),
            )
        ),
        grant_id="grant-events",
        device_id="device-local",
    )

    assert len(runtime.attention_tracker.cursor) == 0
    expired_reference = runtime.reference_resolver.get(
        reference.reference_id,
        owner_id=runtime.config.owner_id,
        device_id="device-local",
        project_id=runtime.config.project_id,
    )
    assert expired_reference.spatial_expires_at == now + timedelta(milliseconds=600)
    assert result.context_invalidation_count == 2
    assert result.decisions[1].invalidated_targets == 1
    with pytest.raises(DesktopTargetError, match="unavailable"):
        runtime.desktop_targets.get(
            target.target_id,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
        )


@pytest.mark.asyncio
async def test_api_is_scoped_and_rejects_spoofed_task_events_without_consuming_grant(
    event_runtime: tuple[SoraRuntime, FakeDesktopEventSource],
) -> None:
    runtime, _ = event_runtime
    authorization = await persist_operation_grant(
        runtime,
        "desktop.observe:events",
        grant_id="grant-api-events",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    handler = RouteHandler(runtime)
    now = datetime.now(UTC)
    response = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/events",
            headers={
                "x-sora-grant-id": "grant-api-events",
                "x-sora-device-id": "device-local",
            },
            body=DesktopEventBatch(
                events=(desktop_event("api-event", DesktopEventKind.WINDOW_OPENED, now),)
            ).model_dump_json().encode(),
        )
    )
    assert response.status_code == 200
    assert response.parse_json()["accepted_count"] == 1

    spoofed = DesktopEventBatch(
        events=(
            DesktopEvent(
                event_id="spoofed-task",
                kind=DesktopEventKind.TASK_CHANGED,
                occurred_at=now,
                task_id="task-not-canonical",
                task_status=TaskStatus.COMPLETED,
            ),
        )
    )
    rejected = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/events",
            headers={
                "x-sora-grant-id": "grant-api-events",
                "x-sora-device-id": "device-local",
            },
            body=spoofed.model_dump_json().encode(),
        )
    )
    assert rejected.status_code == 409
    persisted = await runtime.repository.get_grant(authorization.grant.grant_id)
    assert persisted is not None and persisted.used_count == 0


@pytest.mark.asyncio
async def test_subscription_rechecks_revocation_and_stops_cleanly(
    event_runtime: tuple[SoraRuntime, FakeDesktopEventSource],
) -> None:
    runtime, source = event_runtime
    authorization = await persist_operation_grant(
        runtime,
        "desktop.observe:events",
        grant_id="grant-subscription",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    started = await runtime.start_desktop_event_subscription(
        grant_id="grant-subscription", device_id="device-local"
    )
    assert started["status"] == "running" and source.running

    now = datetime.now(UTC)
    source.emit(desktop_event("subscribed-event", DesktopEventKind.FOREGROUND_CHANGED, now))
    async with asyncio.timeout(1):
        while not any(
            event.event_id == "subscribed-event"
            for event in runtime.desktop_event_policy.recent
        ):
            await asyncio.sleep(0.005)
    assert any(
        event.event_id == "subscribed-event" for event in runtime.desktop_event_policy.recent
    )

    await runtime.repository.save_grant(
        authorization.grant.model_copy(update={"status": GrantStatus.REVOKED})
    )
    source.emit(
        desktop_event(
            "revoked-event",
            DesktopEventKind.FOREGROUND_CHANGED,
            now + timedelta(seconds=1),
        )
    )
    async with asyncio.timeout(1):
        while source.running:
            await asyncio.sleep(0.005)
    assert not any(
        event.event_id == "revoked-event" for event in runtime.desktop_event_policy.recent
    )
    stopped = await runtime.stop_desktop_event_subscription()
    assert stopped == {"status": "stopped", "was_running": False}
    assert not source.running


@pytest.mark.asyncio
async def test_canonical_task_changes_share_policy_without_context_invalidation(
    event_runtime: tuple[SoraRuntime, FakeDesktopEventSource],
) -> None:
    runtime, _ = event_runtime
    receipt = await runtime.submit_task(
        "Inspect the deterministic fixture",
        idempotency_key="desktop-event-task-fixture",
        explicit_provider="deterministic",
    )
    report = await runtime.wait_for_task(receipt.task.task_id, timeout=2)
    assert report.completed
    task_events = tuple(
        event
        for event in runtime.desktop_event_policy.recent
        if event.kind is DesktopEventKind.TASK_CHANGED
    )
    assert len(task_events) == 2
    assert all(event.event_id.startswith("task-event:") for event in task_events)
    assert task_events[-1].attention_hint is DesktopAttentionHint.NOTICE
    assert not any(event.context_invalidated for event in task_events)


@pytest.mark.skipif(os.name != "nt", reason="WinEventHook is Windows-only")
def test_native_windows_event_source_starts_and_stops() -> None:
    source = WindowsDesktopEventSource()
    source.start(lambda _event: None, device_id="device-local", topology_revision=lambda: 1)
    time.sleep(0.05)
    assert source.running
    source.stop()
    assert not source.running
