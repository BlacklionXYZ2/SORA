from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.contracts.models import ProviderRequest
from sora.providers.claude_code import ClaudeCodeProvider
from sora.providers.process_tree import OwnedProcess
from sora.providers.windows_job import job_active_processes, job_name

windows_only = pytest.mark.skipif(os.name != "nt", reason="Windows job objects")

# Shaped like npm's claude.CMD: cmd.exe starts the real, long-running program as a child.
# (Microsoft Store Python cannot be the child: Windows starts Store apps outside any job.)
SHIM = "@echo off\r\nping -n 120 -w 1000 127.0.0.1 > nul\r\n"


async def _tree_running(run_id: str) -> int:
    """Wait until cmd.exe and its child ping are both inside the run's job."""
    for _ in range(200):
        count = job_active_processes(job_name(run_id))
        if count is not None and count >= 2:
            return count
        await asyncio.sleep(0.05)
    raise AssertionError(f"tree never started: {job_active_processes(job_name(run_id))}")


@windows_only
@pytest.mark.asyncio
async def test_stop_kills_the_whole_tree_not_just_the_shim(tmp_path: Path) -> None:
    shim = tmp_path / "agent.cmd"
    shim.write_text(SHIM, encoding="ascii")
    owned = await OwnedProcess.start([str(shim)], run_id="run-tree-1", cwd=str(tmp_path))
    try:
        await _tree_running("run-tree-1")
        assert not owned.stopped()
        started = time.monotonic()
        assert await owned.stop()
        assert time.monotonic() - started < 10  # Not waiting for ping's two minutes.
        assert owned.stopped()
        assert job_active_processes(job_name("run-tree-1")) == 0
    finally:
        owned.close()


@pytest.mark.asyncio
async def test_missing_program_fails_at_start(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        await OwnedProcess.start([str(tmp_path / "missing.exe")], run_id="run-tree-2", cwd=None)


@windows_only
@pytest.mark.asyncio
async def test_claude_cancel_stops_the_real_agent_behind_the_shim(tmp_path: Path) -> None:
    shim = tmp_path / "claude.cmd"
    shim.write_text(SHIM, encoding="ascii")
    provider = ClaudeCodeProvider(command=str(shim), cwd=str(tmp_path), timeout_seconds=60)
    request = ProviderRequest.model_validate({
        "request_id": "request-tree", "task_id": "task-tree", "run_id": "run-tree-3",
        "owner_id": "owner-local", "project_id": "project-sora", "intent": "Wait",
        "context": "fixture", "context_manifest_ref": "context-tree",
        "deadline": datetime.now(UTC) + timedelta(seconds=60),
        "artifact_destination": str(tmp_path), "idempotency_key": "provider-start-tree",
    })
    run_id = await provider.start(request)
    await _tree_running(run_id)
    assert not provider.writer_stopped(run_id)
    started = time.monotonic()
    await provider.cancel(run_id)
    assert time.monotonic() - started < 10
    assert provider.writer_stopped(run_id)
    assert job_active_processes(job_name(run_id)) == 0
