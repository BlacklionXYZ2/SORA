"""Transport bounds use real child processes, including hung and malformed workers."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

from sora.contracts.desktop import DesktopObservationRequest
from sora.desktop.bridge import WindowsObservationBridge


@pytest.mark.asyncio
@pytest.mark.parametrize(("script", "expected"), [
    ("import time; time.sleep(60)", "timeout"),
    ("print('not-json')", "protocol_error"),
    ("print('x'*600000)", "protocol_error"),
    ("print('{}'); print('{}')", "protocol_error"),
    ("print('{\"status\":\"access_denied\"}')", "access_denied"),
    ("print('{\"status\":\"elevated_target\"}')", "elevated_target"),
])
async def test_bounded_workers(
    monkeypatch: pytest.MonkeyPatch, script: str, expected: str,
) -> None:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await original(sys.executable, "-c", script, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsObservationBridge(Path(sys.executable), timeout=0.5)
    result = await bridge.observe(DesktopObservationRequest(operation="windows", process_id=1))
    assert result.status == expected
    assert not result.nodes
    assert children[0].returncode is not None


@pytest.mark.asyncio
async def test_cancellation_and_busy_reap_worker(monkeypatch: pytest.MonkeyPatch) -> None:
    original = asyncio.create_subprocess_exec
    launched = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        process = await original(sys.executable, "-c", "import time;time.sleep(60)", **kwargs)
        children.append(process)
        launched.set()
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsObservationBridge(Path(sys.executable))
    request = DesktopObservationRequest(operation="windows", process_id=1)
    task = asyncio.create_task(bridge.observe(request))
    await launched.wait()
    assert (await bridge.observe(request)).status == "busy"
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[0].returncode is not None


def test_invalid_targets_and_bounds() -> None:
    invalid_fields: list[dict[str, Any]] = [
        {"operation": "tree"}, {"operation": "invoke"},
        {"operation": "windows", "window_handle": 1},
        {"operation": "windows", "max_nodes": 257},
        {"operation": "windows", "max_depth": 13},
    ]
    for fields in invalid_fields:
        with pytest.raises(ValueError):
            DesktopObservationRequest.model_validate({"process_id": 1, **fields})
