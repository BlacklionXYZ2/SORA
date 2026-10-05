"""Static delegation revocation across queues, restart, remote runs and fan-out."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from sora.contracts.models import (
    NormalizedResult,
    ProviderOutcome,
    ProviderRequest,
    RunStatus,
    TaskStatus,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


class HeldProvider(DeterministicProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def start(self, request: ProviderRequest) -> str:
        result = await super().start(request)
        self.started.set()
        return result

    async def _produce(self, request: ProviderRequest) -> NormalizedResult:
        await self.release.wait()
        return await super()._produce(request)

    async def cancel(self, run_id: str) -> None:
        await super().cancel(run_id)
        self.release.set()


def toggle(settings: AppSettingsController, enabled: bool) -> None:
    settings.save(SettingsEdit(version=3, expected_revision=settings.saved.revision,
        changes={"local_companion.agent_delegation": enabled}))


def runtime_for(tmp_path: Path, provider: DeterministicProvider) -> SoraRuntime:
    return SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT, worker_count=1),
        provider=provider, app_settings=AppSettingsController(tmp_path, AppSettings()))


@pytest.mark.asyncio
async def test_off_on_cancels_active_and_never_launches_queued_local_work(tmp_path: Path) -> None:
    provider = HeldProvider()
    runtime = runtime_for(tmp_path, provider)
    await runtime.start()
    assert runtime.app_settings is not None
    try:
        with owner_local_scope():
            first = await runtime.submit_task("Explain queues")
            await asyncio.wait_for(provider.started.wait(), 2)
            second = await runtime.submit_task("Explain persistence")
        assert first.run.local_delegation_epoch == second.run.local_delegation_epoch == 0
        toggle(runtime.app_settings, False)
        toggle(runtime.app_settings, True)
        reports = await asyncio.gather(runtime.wait_for_task(first.task.task_id),
                                       runtime.wait_for_task(second.task.task_id))
        assert all(report.status is TaskStatus.CANCELLED for report in reports)
        assert provider.start_count == 1
        with owner_local_scope():
            third = await runtime.submit_task("New explicit request")
        assert third.run.local_delegation_epoch == 2
        assert (await runtime.wait_for_task(third.task.task_id)).status is TaskStatus.COMPLETED
    finally:
        provider.release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_pending_local_policy_is_persisted_and_checked_after_restart(tmp_path: Path) -> None:
    runtime = runtime_for(tmp_path, DeterministicProvider())
    await runtime.start()
    assert runtime.app_settings is not None
    receipt = await runtime.runtime_repository.submit(
        owner_id=runtime.config.owner_id, project_id=runtime.config.project_id,
        conversation_id=runtime.config.conversation_id, intent="Queued before restart",
        idempotency_key="restart-policy", now=datetime.now(UTC),
        provider="deterministic-mock", local_delegation_epoch=0,
    )
    toggle(runtime.app_settings, False)
    toggle(runtime.app_settings, True)
    await runtime.close()
    provider = DeterministicProvider()
    restarted = runtime_for(tmp_path, provider)
    await restarted.start()
    try:
        report = await restarted.wait_for_task(receipt.task.task_id)
        assert report.status is TaskStatus.CANCELLED and provider.start_count == 0
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_remote_or_legacy_run_is_not_converted_to_local_policy(tmp_path: Path) -> None:
    provider = HeldProvider()
    runtime = runtime_for(tmp_path, provider)
    await runtime.start()
    assert runtime.app_settings is not None
    try:
        receipt = await runtime.submit_task("Remote-authorized fixture request")
        assert receipt.run.local_delegation_epoch is None
        await asyncio.wait_for(provider.started.wait(), 2)
        toggle(runtime.app_settings, False)
        assert not provider._cancelled
        provider.release.set()
        assert (await runtime.wait_for_task(receipt.task.task_id)).status is TaskStatus.COMPLETED
    finally:
        provider.release.set()
        await runtime.close()


@pytest.mark.asyncio
async def test_resume_or_fallback_cannot_launch_an_old_local_request(tmp_path: Path) -> None:
    provider = DeterministicProvider()
    runtime = runtime_for(tmp_path, provider)
    await runtime.start()
    assert runtime.app_settings is not None
    try:
        receipt = await runtime.runtime_repository.submit(
            owner_id=runtime.config.owner_id, project_id=runtime.config.project_id,
            conversation_id=runtime.config.conversation_id, intent="Delayed resume",
            idempotency_key="resume-policy", now=datetime.now(UTC),
            provider="deterministic-mock", local_delegation_epoch=0,
        )
        request = await runtime._provider_request(
            receipt.task, receipt.run.run_id, datetime.now(UTC)
        )
        toggle(runtime.app_settings, False)
        toggle(runtime.app_settings, True)
        launch = AsyncMock()
        with pytest.raises(OperationAuthorizationError, match="changed"):
            await runtime._policy_launch(provider, request, launch)
        launch.assert_not_awaited()
    finally:
        await runtime.close()


def test_disk_edits_preserve_monotonic_delegation_epoch(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(SettingsEdit(version=3, expected_revision=0,
        changes={"dialogue.timeout_seconds": 60}))
    assert settings.saved.delegation_epoch == 0
    for enabled, expected_epoch in ((False, 1), (True, 2)):
        data = json.loads(settings.store.path.read_text())
        data["local_companion"]["agent_delegation"] = enabled
        data["delegation_epoch"] = 0  # An old editor must not roll the counter backwards.
        settings.store.path.write_text(json.dumps(data), encoding="utf-8")
        settings.refresh()
        assert settings.saved.delegation_epoch == expected_epoch
        assert settings.active.delegation_epoch == expected_epoch
    restarted = AppSettingsController(tmp_path, AppSettings())
    assert restarted.saved.delegation_epoch == 2


@pytest.mark.asyncio
async def test_fanout_branches_keep_local_epoch_and_receive_cancellation(tmp_path: Path) -> None:
    provider = HeldProvider()
    runtime = runtime_for(tmp_path, provider)
    await runtime.start()
    assert runtime.app_settings is not None
    task: asyncio.Task[object] | None = None
    try:
        with owner_local_scope():
            task = asyncio.create_task(runtime.run_fanout("Compare ideas", providers=("default",)))
        await asyncio.wait_for(provider.started.wait(), 2)
        toggle(runtime.app_settings, False)
        await asyncio.wait_for(task, 5)
        tasks = await runtime.runtime_repository.list_tasks()
        runs = await runtime.runtime_repository.list_runs(tasks[0].task_id)
        branches = [run for run in runs if run.run_id.endswith("-b0")]
        assert len(branches) == 1
        assert branches[0].local_delegation_epoch == 0
        assert branches[0].status is RunStatus.CANCELLED
    finally:
        provider.release.set()
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_first", [True, False])
async def test_cancel_and_worker_admission_are_atomic(tmp_path: Path, cancel_first: bool) -> None:
    runtime = runtime_for(tmp_path, DeterministicProvider())
    await runtime.start()
    try:
        now = datetime.now(UTC)
        receipt = await runtime.runtime_repository.submit(
            owner_id=runtime.config.owner_id, project_id=runtime.config.project_id,
            conversation_id=runtime.config.conversation_id, intent="Race cancellation with lease",
            idempotency_key="atomic-cancel", now=now, provider="deterministic-mock",
            local_delegation_epoch=0,
        )
        cancel = runtime.runtime_repository.request_cancel(receipt.run.run_id, now)
        admit = runtime.runtime_repository.acquire_lease(receipt.run.run_id,
            lease_owner="fixture-worker", now=now, expires_at=now + timedelta(seconds=30),
            deadline=now + timedelta(seconds=30))
        await asyncio.gather(*( (cancel, admit) if cancel_first else (admit, cancel) ))
        run = await runtime.runtime_repository.get_run(receipt.run.run_id)
        assert run is not None and run.status in {RunStatus.CANCELLED, RunStatus.CANCEL_REQUESTED}
        assert not await runtime.runtime_repository.request_cancel(receipt.run.run_id, now)
        if run.status is RunStatus.CANCEL_REQUESTED:
            await runtime.runtime_repository.mark_running(run.run_id, now)
            current = await runtime.runtime_repository.get_run(run.run_id)
            assert current is not None and current.status is RunStatus.CANCEL_REQUESTED
            await runtime.runtime_repository.finish(run.run_id, run_status=RunStatus.CANCELLED,
                task_status=TaskStatus.CANCELLED, outcome=ProviderOutcome.CANCELLED,
                result_ref=None, now=now)
    finally:
        await runtime.close()
