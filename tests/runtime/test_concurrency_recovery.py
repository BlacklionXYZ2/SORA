from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.contracts.models import RunStatus, TaskStatus
from sora.identity.loader import load_identity
from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from sora.providers.mock import DeterministicProvider
from sora.runtime.repository import RuntimeRepository
from sora.runtime.service import RuntimeConfig, SoraRuntime

from .helpers import IDENTITY_ROOT, make_runtime, wait_for_status


@pytest.mark.asyncio
async def test_slow_reasoning_does_not_block_unrelated_dialogue_or_fabricate_result(
    tmp_path: Path,
) -> None:
    runtime, _ = make_runtime(tmp_path, delay=0.15)
    await runtime.start()
    receipt = await runtime.submit_task("Perform a deliberately slow analysis.")
    chunks = [chunk async for chunk in runtime.stream_dialogue("Meanwhile, hello.")]
    response = "".join(chunks)
    pending = await runtime.report(receipt.task.task_id)

    assert "Meanwhile, hello." in response
    assert len(chunks) > 1
    assert not pending.completed
    assert "no completed result" in pending.message

    completed = await runtime.wait_for_task(receipt.task.task_id)
    await runtime.close()
    assert completed.completed


@pytest.mark.asyncio
async def test_active_task_capacity_rejects_overload_without_partial_submission(
    tmp_path: Path,
) -> None:
    runtime, _ = make_runtime(tmp_path, delay=0.1, workers=1, queue_capacity=1)
    await runtime.start()
    first = await runtime.submit_task("Occupy the one-task runtime capacity.")
    await wait_for_status(runtime, first.task.task_id, TaskStatus.REASONING)

    with pytest.raises(RuntimeError, match="capacity 1"):
        await runtime.submit_task("This task must not be partially persisted.")
    assert len(await runtime.runtime_repository.list_tasks()) == 1

    await runtime.wait_for_task(first.task.task_id)
    second = await runtime.submit_task("Capacity is available after completion.")
    await runtime.wait_for_task(second.task.task_id)
    await runtime.close()

    assert len(await runtime.runtime_repository.list_tasks()) == 2


@pytest.mark.asyncio
async def test_restart_reconciles_orphaned_unexpired_lease_without_relaunch(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "data" / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.register_conversation("conversation-main", "owner-local", "project-sora")
    await repository.activate_identity("owner-local", load_identity(IDENTITY_ROOT), source="test")
    runtime_repository = RuntimeRepository(repository)
    now = datetime.now(UTC)
    submitted_at = now - timedelta(seconds=1)
    receipt = await runtime_repository.submit(
        owner_id="owner-local",
        project_id="project-sora",
        conversation_id="conversation-main",
        intent="Simulate a process crash after lease acquisition.",
        idempotency_key="crash-once",
        now=submitted_at,
        provider="deterministic-mock",
    )
    assert await runtime_repository.acquire_lease(
        receipt.run.run_id,
        lease_owner="dead-worker",
        now=now,
        expires_at=now + timedelta(seconds=30),
        deadline=now + timedelta(seconds=10),
    )

    provider = DeterministicProvider()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider,
    )
    reconciled = await runtime.start()
    run = await runtime.runtime_repository.get_run(receipt.run.run_id)
    task = await runtime.runtime_repository.get_task(receipt.task.task_id)
    await runtime.close()

    assert reconciled == [receipt.run.run_id]
    assert run is not None and run.status is RunStatus.INTERRUPTED
    assert task is not None and task.status is TaskStatus.INTERRUPTED
    assert await runtime.runtime_repository.lease_count() == 0
    assert provider.start_count == 0


@pytest.mark.asyncio
async def test_cancelled_result_is_retained_but_patch_is_not_applied(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, delay=0.1)
    await runtime.start()
    receipt = await runtime.submit_task("Wait until cancellation.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)
    assert await runtime.cancel(receipt.task.task_id)

    report = await runtime.wait_for_task(receipt.task.task_id)
    counts = await runtime.repository.counts()
    await runtime.close()

    assert report.status is TaskStatus.CANCELLED
    assert report.result is not None
    assert counts["normalized_results"] == 1
    assert counts["facts"] == 0
