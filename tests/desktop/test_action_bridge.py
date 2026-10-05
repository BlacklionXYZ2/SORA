"""Bounds and protocol checks for the one-shot P11.3 native action worker."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sora.desktop import WindowsActionBridge, WindowsPressRequest


def request() -> WindowsPressRequest:
    return WindowsPressRequest(
        process_id=123,
        process_started_at=datetime(2026, 9, 15, tzinfo=UTC),
        root_window_handle=456,
        native_window_handle=789,
        runtime_id=(42, 7),
        automation_id="fixture-confirm",
        control_type="ControlType.Button",
        expected_x=10,
        expected_y=20,
        expected_width=100,
        expected_height=30,
        expected_name_before="Confirm fixture",
        expected_name_after="Confirmed once",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("script", "status", "attempted"),
    [
        ("import time; time.sleep(60)", "unknown_outcome", True),
        ("print('not-json')", "unknown_outcome", True),
        ("print('{}'); print('{}')", "unknown_outcome", True),
        (
            "print('{\"status\":\"unavailable\",\"effect_attempted\":false,\"verified\":false}')",
            "unavailable",
            False,
        ),
        (
            "print('{\"status\":\"verified\",\"effect_attempted\":false,\"verified\":true}')",
            "unknown_outcome",
            True,
        ),
    ],
)
async def test_action_worker_is_bounded_and_protocol_checked(
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
    bridge = WindowsActionBridge(Path(sys.executable), timeout=0.5)
    result = await bridge.press(request())
    assert result.status == status
    assert result.effect_attempted is attempted
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_action_worker_cancellation_reaps_child(monkeypatch: pytest.MonkeyPatch) -> None:
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await original(sys.executable, "-c", "import time;time.sleep(60)", **kwargs)
        children.append(process)
        launched.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsActionBridge(Path(sys.executable))
    task = asyncio.create_task(bridge.press(request()))
    await launched.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None
