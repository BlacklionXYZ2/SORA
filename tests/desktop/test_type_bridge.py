"""Bounds and protocol checks for the one-shot P11.5 native TYPE worker."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sora.desktop import WindowsTypeBridge, WindowsTypeRequest


def request() -> WindowsTypeRequest:
    return WindowsTypeRequest(
        process_id=123,
        process_started_at=datetime(2026, 9, 16, tzinfo=UTC),
        root_window_handle=456,
        native_window_handle=789,
        runtime_id=(88, 9),
        automation_id="fixture-text",
        control_type="ControlType.Edit",
        expected_x=30,
        expected_y=100,
        expected_width=240,
        expected_height=30,
        expected_name_before="Fixture text",
        text="bounded text",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("script", "status", "attempted"),
    [
        ("import time; time.sleep(60)", "unknown_outcome", True),
        ("print('not-json')", "unknown_outcome", True),
        ("print('{}'); print('{}')", "unknown_outcome", True),
        (
            "print('{\"status\":\"unavailable\",\"effect_attempted\":false,"
            "\"verified\":false}')",
            "unavailable",
            False,
        ),
        (
            "print('{\"status\":\"verified\",\"effect_attempted\":false,"
            "\"verified\":true}')",
            "unknown_outcome",
            True,
        ),
    ],
)
async def test_type_worker_is_bounded_and_protocol_checked(
    monkeypatch: pytest.MonkeyPatch,
    script: str,
    status: str,
    attempted: bool,
) -> None:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await original(sys.executable, "-c", script, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsTypeBridge(Path(sys.executable), timeout=0.5)
    result = await bridge.type_text(request())
    assert result.status == status
    assert result.effect_attempted is attempted
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_type_worker_cancellation_reaps_child(monkeypatch: pytest.MonkeyPatch) -> None:
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await original(sys.executable, "-c", "import time;time.sleep(60)", **kwargs)
        children.append(process)
        launched.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsTypeBridge(Path(sys.executable))
    task = asyncio.create_task(bridge.type_text(request()))
    await launched.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None
