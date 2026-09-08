from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta

import pytest

from sora.attention.buffer import CursorRingBuffer, CursorSample
from sora.attention.gestures import detect_hover, recognize_circle
from sora.contracts.models import (
    AttentionTarget,
    DesktopObjectRecord,
    DesktopObjectVisibility,
    TaskRecord,
    TaskStatus,
)
from sora.desktop_objects.kanban import KanbanColumn, project_tasks_to_kanban


def test_cursor_ring_buffer_operations() -> None:
    buf = CursorRingBuffer(capacity=5)
    base_time = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)

    for i in range(8):
        sample = CursorSample(
            timestamp=base_time + timedelta(seconds=i),
            x=100 + i * 5,
            y=200 + i * 5,
        )
        buf.append(sample)

    # Max length is 5; oldest 3 dropped
    assert len(buf) == 5

    # Sample at exact timestamp t + 5s (which is in buffer)
    hit = buf.get_sample_at(base_time + timedelta(seconds=5), tolerance_seconds=0.1)
    assert hit is not None
    assert hit.x == 125

    # Sample at t + 1s was dropped
    miss = buf.get_sample_at(base_time + timedelta(seconds=1), tolerance_seconds=0.1)
    assert miss is None

    # Sample with wide tolerance can find closest
    closest = buf.get_sample_at(base_time + timedelta(seconds=1), tolerance_seconds=10.0)
    assert closest is not None
    assert closest.timestamp == base_time + timedelta(seconds=3)

    # get_recent_samples
    recent = buf.get_recent_samples(
        duration_seconds=2.0,
        now=base_time + timedelta(seconds=7),
    )
    assert len(recent) == 3
    assert [s.timestamp for s in recent] == [
        base_time + timedelta(seconds=5),
        base_time + timedelta(seconds=6),
        base_time + timedelta(seconds=7),
    ]


def test_cursor_ring_buffer_rejects_naive_timestamp() -> None:
    buf = CursorRingBuffer(capacity=5)
    naive = CursorSample(
        timestamp=datetime(2026, 9, 8, 12, 0, 0),  # no tzinfo
        x=10,
        y=10,
    )
    with pytest.raises(ValueError, match="UTC offset"):
        buf.append(naive)


def test_detect_hover_gesture() -> None:
    base_time = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)

    # Hovering: 10 samples within 5px over 0.9s
    hover_samples = tuple(
        CursorSample(
            timestamp=base_time + timedelta(seconds=i * 0.1),
            x=100 + (i % 3),
            y=200 + (i % 2),
        )
        for i in range(10)
    )
    centroid = detect_hover(hover_samples, min_duration_seconds=0.5, max_distance_px=10.0)
    assert centroid is not None
    assert centroid == (100, 200)

    # Moving too fast: distance exceeds threshold
    moving_samples = tuple(
        CursorSample(
            timestamp=base_time + timedelta(seconds=i * 0.1),
            x=100 + i * 15,
            y=200,
        )
        for i in range(10)
    )
    assert detect_hover(moving_samples, min_duration_seconds=0.5, max_distance_px=10.0) is None

    # Too short duration
    short_samples = hover_samples[:3]  # 0.2s
    assert detect_hover(short_samples, min_duration_seconds=0.5, max_distance_px=10.0) is None


def test_recognize_circle_gesture() -> None:
    base_time = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    cx, cy, radius = 250, 250, 60
    n_points = 32

    # Form a closed circular trajectory
    circle_samples = tuple(
        CursorSample(
            timestamp=base_time + timedelta(seconds=i * 0.05),
            x=int(cx + radius * math.cos(2 * math.pi * i / n_points)),
            y=int(cy + radius * math.sin(2 * math.pi * i / n_points)),
        )
        for i in range(n_points + 1)
    )

    bbox = recognize_circle(circle_samples)
    assert bbox is not None
    min_x, min_y, width, height = bbox
    assert 185 <= min_x <= 195
    assert 185 <= min_y <= 195
    assert 110 <= width <= 130
    assert 110 <= height <= 130

    # Linear trajectory is rejected
    linear_samples = tuple(
        CursorSample(
            timestamp=base_time + timedelta(seconds=i * 0.05),
            x=100 + i * 10,
            y=100 + i * 10,
        )
        for i in range(n_points)
    )
    assert recognize_circle(linear_samples) is None

    # Too few points rejected
    assert recognize_circle(circle_samples[:5]) is None


def test_attention_target_and_desktop_object_contracts() -> None:
    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)
    target = AttentionTarget(
        target_id="target-1",
        source="circle",
        created_at=now,
        expires_at=now + timedelta(minutes=5),
        owner_id="owner-test",
        device_id="device-test",
        screen_rect=(100, 100, 200, 200),
        confidence=0.95,
    )
    assert target.source == "circle"
    assert target.screen_rect == (100, 100, 200, 200)

    # Disallow expires_at preceding created_at
    with pytest.raises(ValueError, match="expires_at cannot precede created_at"):
        AttentionTarget(
            target_id="target-invalid",
            source="hover",
            created_at=now,
            expires_at=now - timedelta(seconds=1),
            owner_id="owner-test",
            device_id="device-test",
        )

    obj = DesktopObjectRecord(
        object_id="kanban-desk-1",
        object_type="kanban_board",
        owner_id="owner-test",
        anchor="top_right_display",
        visibility=DesktopObjectVisibility.LOCAL_ONLY,
        affordances=("click", "drag", "expand"),
    )
    assert obj.visibility is DesktopObjectVisibility.LOCAL_ONLY
    assert "drag" in obj.affordances


def test_kanban_board_projection() -> None:
    now = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)

    tasks = (
        TaskRecord(
            task_id="task-q",
            owner_id="owner-1",
            creator_message_id="msg-1",
            status=TaskStatus.QUEUED,
            base_revision=0,
            constraints=("Pending work item",),
            created_at=now,
            updated_at=now,
        ),
        TaskRecord(
            task_id="task-perm",
            owner_id="owner-1",
            creator_message_id="msg-2",
            status=TaskStatus.WAITING_FOR_PERMISSION,
            base_revision=0,
            constraints=("Needs file grant",),
            created_at=now,
            updated_at=now,
        ),
        TaskRecord(
            task_id="task-run",
            owner_id="owner-1",
            creator_message_id="msg-3",
            status=TaskStatus.REASONING,
            effective_backend="hermes",
            base_revision=0,
            constraints=("Ongoing reasoning",),
            created_at=now,
            updated_at=now,
        ),
        TaskRecord(
            task_id="task-done",
            owner_id="owner-1",
            creator_message_id="msg-4",
            status=TaskStatus.COMPLETED,
            result_ref="res-1",
            base_revision=0,
            constraints=("Finished successfully",),
            created_at=now,
            updated_at=now,
        ),
        TaskRecord(
            task_id="task-err",
            owner_id="owner-1",
            creator_message_id="msg-5",
            status=TaskStatus.FAILED,
            base_revision=0,
            constraints=("Failed with error",),
            created_at=now,
            updated_at=now,
        ),
    )

    board = project_tasks_to_kanban(tasks, board_id="kanban-custom")
    assert board.board_id == "kanban-custom"
    assert len(board.cards) == 5

    by_id = {c.task_id: c for c in board.cards}

    assert by_id["task-q"].column is KanbanColumn.TODO
    assert not by_id["task-q"].needs_attention

    assert by_id["task-perm"].column is KanbanColumn.TODO
    assert by_id["task-perm"].needs_attention

    assert by_id["task-run"].column is KanbanColumn.DOING
    assert by_id["task-run"].specialist == "hermes"
    assert not by_id["task-run"].needs_attention

    assert by_id["task-done"].column is KanbanColumn.DONE
    assert not by_id["task-done"].needs_attention

    assert by_id["task-err"].column is KanbanColumn.DONE
    assert by_id["task-err"].needs_attention
