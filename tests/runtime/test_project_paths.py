from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from sora.providers.windows_job import (
    WindowsWriterJob,
    _kernel,
    process_may_be_alive,
    writer_job_empty,
)
from sora.runtime.app_settings import AppSettings, AppSettingsStore
from sora.runtime.project_paths import ProjectPaths, project_directory, snapshot
from sora.runtime.repository import RuntimeRepository


@pytest.mark.asyncio
async def test_atomic_overlap_uncertainty_and_diff(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "state.db")
    await database.initialize()
    await database.write(
        lambda db: (
            db.execute("INSERT INTO owners VALUES ('owner', 'fixture')"),
            db.execute("INSERT INTO projects VALUES ('project', 'owner', 'fixture')"),
            db.execute(
                "INSERT INTO conversations VALUES ('conversation', 'owner', 'project', 'fixture')"
            ),
        )
    )
    repository = RuntimeRepository(SoraRepository(database))
    receipts = [
        await repository.submit(
            owner_id="owner",
            project_id="project",
            conversation_id="conversation",
            intent="fixture",
            idempotency_key=f"fixture-{i}",
            now=datetime.now(UTC),
            provider="codex",
        )
        for i in range(3)
    ]
    project = tmp_path / "project"
    nested = project / "nested"
    nested.mkdir(parents=True)
    paths = ProjectPaths(database)
    first, second, third = receipts
    results = await asyncio.gather(
        paths.acquire(first.run.run_id, first.task.task_id, project),
        paths.acquire(second.run.run_id, second.task.task_id, nested),
    )
    assert sorted(results) == [False, True]
    winner = first if results[0] else second
    await paths.settle(winner.run.run_id, stopped=False)
    assert not await paths.acquire(third.run.run_id, third.task.task_id, project)
    assert (await paths.projection())["leases"][0]["status"] == "uncertain"
    # Live Core reservation remains held even when no job has started yet.
    await paths.reconcile()
    assert len((await paths.projection())["leases"]) == 1
    await paths.settle(winner.run.run_id, stopped=True)
    assert await paths.acquire(third.run.run_id, third.task.task_id, project)
    before = snapshot(project)
    (project / "written.txt").write_text("new")
    await paths.record_diff(third.run.run_id, before)
    event = (await paths.projection())["events"][0]
    assert event["source"] == "filesystem_diff" and event["operation"] == "file.created"
    assert not snapshot(project, limit=0).complete
    await paths.record_diff(third.run.run_id, snapshot(project, limit=0))
    assert (await paths.projection())["events"][0]["operation"] == "file.discovered"
    # Simulated dead Core: kernel accounting must still block a surviving writer.
    if os.name == "nt":
        await database.write(lambda db: db.execute(
            "UPDATE path_leases SET owner_pid=0 WHERE run_id=?", (third.run.run_id,),
        ))
        held_job = WindowsWriterJob("Local\\SORAWriter_" + third.run.run_id)
        bootstrap = Path(__file__).resolve().parents[2] / "src/sora/providers/writer_bootstrap.py"
        held = subprocess.Popen(
            [str(Path(sys.base_prefix) / "python.exe"), str(bootstrap)],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            held_job.attach(held.pid)
            await paths.reconcile()
            assert len((await paths.projection())["leases"]) == 1
            assert held_job.stop()
            held.wait(timeout=5)
            await paths.reconcile()
            assert not (await paths.projection())["leases"]
        finally:
            held_job.close()
            if held.poll() is None:
                held.kill()
                held.wait(timeout=5)
            if held.stdin:
                held.stdin.close()


def test_project_validation_and_v7_migration(tmp_path: Path) -> None:
    assert project_directory(str(tmp_path)) == tmp_path.resolve()
    for invalid in ("relative", str(tmp_path / "absent"), str(Path.home()), str(tmp_path.anchor)):
        with pytest.raises(ValueError):
            project_directory(invalid)
    old = AppSettings().model_dump(mode="json")
    old["version"] = 7
    for value in old["agents"].values():
        for key in ("project_root", "workspace_mode", "base_ref", "model_choices"):
            del value[key]
    path = tmp_path / "settings.json"
    original = json.dumps(old)
    path.write_text(original)
    restored = AppSettingsStore(path).load()
    assert restored.version == 9 and restored.agents.codex.project_root == ""
    assert next(tmp_path.glob("settings.v7-*.json")).read_text() == original


@pytest.mark.skipif(os.name != "nt", reason="Windows kernel containment")
def test_job_handshake_contains_descendant_and_kills_tree(tmp_path: Path) -> None:
    name = "Local\\SORAQA_" + str(uuid.uuid4())
    job = WindowsWriterJob(name)
    bootstrap = Path(__file__).resolve().parents[2] / "src/sora/providers/writer_bootstrap.py"
    child_code = (
        "import subprocess,sys,time;"
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);"
        "print(p.pid,flush=True);time.sleep(60)"
    )
    parent = subprocess.Popen(
        [
            str(Path(sys.base_prefix) / "python.exe"),
            str(bootstrap),
            str(Path(sys.base_prefix) / "python.exe"),
            "-c",
            child_code,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    kernel = _kernel()
    child_handle = None
    try:
        job.attach(parent.pid)
        assert parent.stdin is not None and parent.stdout is not None
        assert not writer_job_empty(name)
        with pytest.raises(OSError, match="already exists"):
            WindowsWriterJob(name)
        parent.stdin.write(b"\n")
        parent.stdin.flush()
        child_pid = int(parent.stdout.readline())
        assert process_may_be_alive(child_pid)
        assert job.contains(child_pid), f"Child {child_pid} escaped the owned job"
        # Retain the original process handle: reopening a terminating PID can
        # return access denied (unknown), which must not be interpreted as live/dead.
        child_handle = kernel.OpenProcess(0x00100000, False, child_pid)
        assert child_handle
        assert job.stop()
        assert writer_job_empty(name)
        assert kernel.WaitForSingleObject(child_handle, 5000) == 0
        job.close()
        assert job.wait_empty()
        parent.wait(timeout=5)
    finally:
        if child_handle:
            kernel.CloseHandle(child_handle)
        job.close()
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=5)
        if parent.stdin:
            parent.stdin.close()
        if parent.stdout:
            parent.stdout.close()
