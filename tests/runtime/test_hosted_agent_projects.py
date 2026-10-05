"""Hosted agents other than Codex working directly in an owner-selected project folder.

Owner decision 2026-10-05: hosted agents are trusted with file writes. Core still serialises
writers per project root and records the before/after diff, exactly as for Codex direct mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from sora.contracts.models import TaskStatus
from sora.providers.claude_code import ClaudeCodeProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.runtime.test_coding_workspaces import repository

IDENTITY = Path(__file__).resolve().parents[2] / "identity"

# Stands in for `claude -p`: edits module.py in its working directory and reports it.
FAKE_WRITER = """
import json, os, sys
sys.stdin.read()
with open('module.py', 'a', encoding='utf-8') as handle:
    handle.write('# edited by claude\\n')
answer = {'conclusion': 'Edited module.py', 'files_changed': ['module.py'],
          'changelog_entry': 'Appended a marker comment to module.py.'}
print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False,
                  'result': json.dumps(answer), 'session_id': 's-1', 'cwd': os.getcwd()}))
"""


def _runtime(tmp_path: Path, provider: ClaudeCodeProvider) -> SoraRuntime:
    state = tmp_path / "state"
    return SoraRuntime(
        RuntimeConfig(root=state, identity_root=IDENTITY, worker_count=1),
        providers={"claude": provider},
        app_settings=AppSettingsController(state, AppSettings()),
    )


@pytest.mark.asyncio
async def test_claude_writes_directly_in_the_selected_project(tmp_path: Path) -> None:
    project = repository(tmp_path)
    script = tmp_path / "fake_claude.py"
    script.write_text(FAKE_WRITER, encoding="utf-8")
    elsewhere = tmp_path / "scratch"
    elsewhere.mkdir()
    provider = ClaudeCodeProvider(
        command=sys.executable, args=(str(script),), cwd=str(elsewhere), timeout_seconds=10,
    )
    runtime = _runtime(tmp_path, provider)
    await runtime.start()
    try:
        with owner_local_scope():
            receipt = await runtime.submit_task(
                "Edit file module.py to add a marker comment.",
                explicit_provider="claude",
                working_directory=str(project),
                workspace_mode="direct",
            )
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=15)
        assert report.status is TaskStatus.COMPLETED, report.message
        assert "# edited by claude" in (project / "module.py").read_text()
        assert not (elsewhere / "module.py").exists()
        # The writer lease is released once the agent's process has exited.
        with owner_local_scope():
            again = await runtime.submit_task(
                "Edit file module.py to add a second marker.",
                explicit_provider="claude",
                working_directory=str(project),
                workspace_mode="direct",
            )
        second = await runtime.wait_for_task(again.task.task_id, timeout=15)
        assert second.status is TaskStatus.COMPLETED, second.message
        assert (project / "module.py").read_text().count("# edited by claude") == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_isolated_worktrees_stay_codex_only(tmp_path: Path) -> None:
    project = repository(tmp_path)
    provider = ClaudeCodeProvider(command=sys.executable, cwd=str(tmp_path), timeout_seconds=5)
    runtime = _runtime(tmp_path, provider)
    await runtime.start()
    try:
        with owner_local_scope(), pytest.raises(ValueError, match="Codex-only"):
            await runtime.submit_task(
                "Edit file module.py to add a marker comment.",
                explicit_provider="claude",
                working_directory=str(project),
                workspace_mode="isolated",
            )
    finally:
        await runtime.close()
