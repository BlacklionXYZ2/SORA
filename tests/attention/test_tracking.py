"""P10.5 volatile cursor, selection, click, hover, and circle acceptance."""

from __future__ import annotations

import math
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.attention import (
    AttentionResolution,
    AttentionResolutionStatus,
    AttentionResolveRequest,
    AttentionTracker,
    CursorSample,
    CursorSampleBatch,
    SelectionSample,
)
from sora.contracts.content import ReferenceResolveRequest
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.models import CapabilityOperation
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


def sample(
    timestamp: datetime,
    x: int,
    y: int,
    *,
    buttons: tuple[str, ...] = (),
    target: str | None = None,
    revision: int = 1,
) -> CursorSample:
    return CursorSample.model_validate(
        {
            "timestamp": timestamp,
            "x": x,
            "y": y,
            "buttons": buttons,
            "target_element": target,
            "topology_revision": revision,
        }
    )


def circle_samples(base: datetime, *, duration: float = 1.6) -> tuple[CursorSample, ...]:
    count = 32
    return tuple(
        sample(
            base + timedelta(seconds=duration * index / count),
            int(400 + 60 * math.cos(2 * math.pi * index / count)),
            int(300 + 60 * math.sin(2 * math.pi * index / count)),
            target="circle-fixture",
        )
        for index in range(count + 1)
    )


def resolve(
    tracker: AttentionTracker,
    source: Literal["hover", "click", "selection", "circle"],
    reference: datetime,
    *,
    now: datetime | None = None,
) -> AttentionResolution:
    return tracker.resolve(
        AttentionResolveRequest.model_validate({"source": source, "reference_time": reference}),
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        topology_revision=1,
        now=now or reference,
    )


def test_bounded_buffer_hover_click_selection_and_explicit_expiry() -> None:
    base = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
    tracker = AttentionTracker(cursor_capacity=6, cursor_max_age_seconds=2)
    hover = tuple(
        sample(
            base + timedelta(milliseconds=100 * index),
            100 + index % 2,
            200,
            target="hover-fixture",
        )
        for index in range(7)
    )
    tracker.append_cursor_batch(CursorSampleBatch(samples=hover))
    assert len(tracker.cursor) == 6
    hovered = resolve(tracker, "hover", hover[-1].timestamp)
    assert hovered.status is AttentionResolutionStatus.RESOLVED
    assert hovered.target is not None
    assert hovered.target.source == "hover"
    assert hovered.target.ui_element == "hover-fixture"
    assert hovered.target.expires_at > hovered.target.created_at

    tracker.clear()
    click = (
        sample(base, 300, 220, target="button-fixture"),
        sample(base + timedelta(milliseconds=50), 301, 220, buttons=("left",)),
        sample(base + timedelta(milliseconds=120), 302, 221, target="button-fixture"),
    )
    tracker.append_cursor_batch(CursorSampleBatch(samples=click))
    clicked = resolve(tracker, "click", click[-1].timestamp)
    assert clicked.status is AttentionResolutionStatus.RESOLVED
    assert clicked.target is not None and clicked.target.screen_rect == (302, 221, 1, 1)

    selection = SelectionSample(
        timestamp=base + timedelta(seconds=1),
        rect=ScreenRect(x=500, y=250, width=240, height=60),
        topology_revision=1,
        desktop_target_id="desktop-target-fixture",
        target_element="selection-fixture",
    )
    tracker.append_selection(selection)
    selected = resolve(tracker, "selection", selection.timestamp)
    assert selected.status is AttentionResolutionStatus.RESOLVED
    assert selected.target is not None
    assert selected.target.screen_rect == (500, 250, 240, 60)
    assert selected.target.desktop_target_id == "desktop-target-fixture"

    expired = resolve(
        tracker,
        "selection",
        selection.timestamp,
        now=selection.timestamp + timedelta(seconds=9),
    )
    assert expired.status is AttentionResolutionStatus.EXPIRED
    assert expired.reason == "selection_expired"

    cursor_expiry = AttentionTracker(cursor_capacity=8, cursor_max_age_seconds=2)
    cursor_expiry.append_cursor_batch(CursorSampleBatch(samples=hover))
    expired_hover = resolve(
        cursor_expiry,
        "hover",
        hover[-1].timestamp,
        now=hover[-1].timestamp + timedelta(seconds=3),
    )
    assert expired_hover.status is AttentionResolutionStatus.EXPIRED
    assert expired_hover.reason == "cursor_samples_expired"

    long_hold = tuple(
        sample(
            base + timedelta(milliseconds=100 * index),
            300,
            220,
            buttons=("left",) if 1 <= index <= 8 else (),
        )
        for index in range(10)
    )
    click_rejected = AttentionTracker(cursor_capacity=16)
    click_rejected.append_cursor_batch(CursorSampleBatch(samples=long_hold))
    rejected_click = resolve(click_rejected, "click", long_hold[-1].timestamp)
    assert rejected_click.status is AttentionResolutionStatus.REJECTED
    assert rejected_click.reason == "click_thresholds_not_met"


def test_circle_geometry_rejects_backtracking_open_slow_and_fast_false_positives() -> None:
    base = datetime(2026, 9, 14, 10, 0, tzinfo=UTC)
    tracker = AttentionTracker(cursor_capacity=128)
    circle = circle_samples(base)
    tracker.append_cursor_batch(CursorSampleBatch(samples=circle))
    circled = resolve(tracker, "circle", circle[-1].timestamp)
    assert circled.status is AttentionResolutionStatus.RESOLVED
    assert circled.target is not None
    assert circled.target.screen_rect == (340, 240, 120, 120)

    rejected_trajectories = (
        # Closed diagonal backtracking has path length but zero enclosed area/winding.
        tuple(
            sample(base + timedelta(milliseconds=50 * index), x, y)
            for index, (x, y) in enumerate(
                (
                    (100, 100),
                    (130, 130),
                    (160, 160),
                    (190, 190),
                    (160, 160),
                    (130, 130),
                    (100, 100),
                    (130, 130),
                    (100, 100),
                )
            )
        ),
        # A three-quarter arc is not closed.
        tuple(circle_samples(base)[:25]),
        circle_samples(base, duration=0.01),
        circle_samples(base, duration=8.0),
    )
    for trajectory in rejected_trajectories:
        candidate = AttentionTracker(cursor_capacity=128, cursor_max_age_seconds=10)
        candidate.append_cursor_batch(CursorSampleBatch(samples=trajectory))
        result = resolve(candidate, "circle", trajectory[-1].timestamp)
        assert result.status is AttentionResolutionStatus.REJECTED
        assert result.reason == "circle_thresholds_not_met"


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await instance.start()
    try:
        yield instance
    finally:
        await instance.close()


async def grant(runtime: SoraRuntime, resource: str, grant_id: str) -> None:
    await persist_operation_grant(
        runtime,
        resource,
        grant_id=grant_id,
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )


@pytest.mark.asyncio
async def test_runtime_api_keeps_raw_samples_out_of_canonical_storage_and_logs(
    runtime: SoraRuntime,
) -> None:
    now = datetime.now(UTC)
    samples = tuple(
        sample(
            now + timedelta(milliseconds=100 * index),
            700 + index % 2,
            400,
            target="sensitive-ui-node-unique",
        )
        for index in range(7)
    )
    await grant(runtime, "desktop.observe:cursor", "grant-cursor-batch")
    await grant(runtime, "desktop.observe:attention", "grant-attention-resolve")
    await grant(runtime, "desktop.observe:selection", "grant-selection-sample")
    await grant(runtime, "desktop.observe:attention", "grant-selection-resolve")
    handler = RouteHandler(runtime)
    ingested = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/attention/cursor",
            headers={
                "x-sora-grant-id": "grant-cursor-batch",
                "x-sora-device-id": "device-local",
            },
            body=CursorSampleBatch(samples=samples).model_dump_json().encode(),
        )
    )
    assert ingested.status_code == 200
    assert ingested.parse_json()["sample_count"] == 7
    resolved = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/attention/resolve",
            headers={
                "x-sora-grant-id": "grant-attention-resolve",
                "x-sora-device-id": "device-local",
            },
            body=AttentionResolveRequest(source="hover", reference_time=samples[-1].timestamp)
            .model_dump_json()
            .encode(),
        )
    )
    assert resolved.status_code == 200
    assert resolved.parse_json()["status"] == "resolved"

    selection = SelectionSample(
        timestamp=now,
        rect=ScreenRect(x=500, y=300, width=120, height=45),
        topology_revision=1,
        target_element="sensitive-selection-unique",
    )
    selection_ingested = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/attention/selection",
            headers={
                "x-sora-grant-id": "grant-selection-sample",
                "x-sora-device-id": "device-local",
            },
            body=selection.model_dump_json().encode(),
        )
    )
    assert selection_ingested.status_code == 200
    selection_resolved = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/attention/resolve",
            headers={
                "x-sora-grant-id": "grant-selection-resolve",
                "x-sora-device-id": "device-local",
            },
            body=AttentionResolveRequest(source="selection", reference_time=selection.timestamp)
            .model_dump_json()
            .encode(),
        )
    )
    assert selection_resolved.status_code == 200
    selection_payload = selection_resolved.parse_json()
    assert selection_payload["status"] == "resolved"
    assert selection_payload["target"]["screen_rect"] == [500, 300, 120, 45]

    # The P10.5 attention result must become P10.6's current referent so a
    # follow-up can delegate work without repeating or guessing the target.
    looked_at = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/references/resolve",
            headers={"x-sora-device-id": "device-local"},
            body=ReferenceResolveRequest(utterance="Look at this").model_dump_json().encode(),
        )
    )
    delegated = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/references/resolve",
            headers={"x-sora-device-id": "device-local"},
            body=ReferenceResolveRequest(utterance="Can Cody fix it").model_dump_json().encode(),
        )
    )
    assert looked_at.status_code == 200
    assert delegated.status_code == 200
    assert looked_at.parse_json()["status"] == "resolved"
    assert delegated.parse_json()["status"] == "resolved"
    assert (
        looked_at.parse_json()["candidate"]["attention_target_id"]
        == selection_payload["target"]["target_id"]
    )
    assert (
        delegated.parse_json()["candidate"]["attention_target_id"]
        == selection_payload["target"]["target_id"]
    )

    trace_fields = await runtime.repository.database.read(
        lambda database: tuple(
            str(row[0]) for row in database.execute("SELECT fields_json FROM traces")
        )
    )
    assert all("sensitive-ui-node-unique" not in fields for fields in trace_fields)
    assert all("sensitive-selection-unique" not in fields for fields in trace_fields)
    database_bytes = (runtime.config.root / "data" / "sora.db").read_bytes()
    assert b"sensitive-ui-node-unique" not in database_bytes
    assert b"sensitive-selection-unique" not in database_bytes

    rect = ScreenRect(x=0, y=0, width=800, height=600)
    runtime.update_embodiment_topology(
        (MonitorDescriptor(id="new", primary=True, rect=rect),), rect
    )
    assert len(runtime.attention_tracker.cursor) == 0
    assert runtime.attention_tracker.selection_count == 0

    runtime.attention_tracker.append_cursor_batch(
        CursorSampleBatch(samples=(sample(datetime.now(UTC), 100, 100, revision=2),))
    )
    runtime.attention_tracker.append_selection(
        SelectionSample(
            timestamp=datetime.now(UTC),
            rect=ScreenRect(x=100, y=100, width=50, height=20),
            topology_revision=2,
        )
    )
    await runtime.close()
    assert len(runtime.attention_tracker.cursor) == 0
    assert runtime.attention_tracker.selection_count == 0


@pytest.mark.asyncio
async def test_runtime_rejects_stale_offscreen_and_unauthorized_capture(
    runtime: SoraRuntime,
) -> None:
    now = datetime.now(UTC)
    stale = CursorSampleBatch(samples=(sample(now, 100, 100, revision=99),))
    await grant(runtime, "desktop.observe:cursor", "grant-cursor-stale")
    with pytest.raises(ValueError, match="stale topology"):
        await runtime.ingest_cursor_samples(
            stale, grant_id="grant-cursor-stale", device_id="device-local"
        )

    offscreen = CursorSampleBatch(samples=(sample(now, 9_999, 9_999),))
    with pytest.raises(ValueError, match="outside active displays"):
        await runtime.ingest_cursor_samples(
            offscreen, grant_id="grant-cursor-stale", device_id="device-local"
        )
    rejected_grant = await runtime.repository.get_grant("grant-cursor-stale")
    assert rejected_grant is not None and rejected_grant.used_count == 0

    await grant(runtime, "desktop.observe:cursor", "grant-cursor-initial")
    initial = CursorSampleBatch(samples=(sample(now + timedelta(milliseconds=200), 100, 100),))
    await runtime.ingest_cursor_samples(
        initial, grant_id="grant-cursor-initial", device_id="device-local"
    )
    await grant(runtime, "desktop.observe:cursor", "grant-cursor-out-of-order")
    out_of_order = CursorSampleBatch(samples=(sample(now + timedelta(milliseconds=100), 100, 100),))
    with pytest.raises(ValueError, match="timestamp order"):
        await runtime.ingest_cursor_samples(
            out_of_order,
            grant_id="grant-cursor-out-of-order",
            device_id="device-local",
        )
    order_grant = await runtime.repository.get_grant("grant-cursor-out-of-order")
    assert order_grant is not None and order_grant.used_count == 0
    assert len(runtime.attention_tracker.cursor) == 1

    valid = CursorSampleBatch(samples=(sample(now + timedelta(milliseconds=300), 100, 100),))
    with pytest.raises(PermissionError):
        await runtime.ingest_cursor_samples(
            valid, grant_id="missing-grant", device_id="device-local"
        )
    assert len(runtime.attention_tracker.cursor) == 1
