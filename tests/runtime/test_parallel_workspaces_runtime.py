from __future__ import annotations

import asyncio
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    ProviderCapabilities,
    ProviderOutcome,
    ProviderRequest,
    RunStatus,
    TaskStatus,
)
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.workspaces import SynthesisConsensus
from tests.authorization_helpers import persist_operation_grant

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def committed_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "source"
    repository.mkdir()
    git(repository, "init")
    git(repository, "config", "user.email", "sora-tests@example.invalid")
    git(repository, "config", "user.name", "SORA Tests")
    (repository / "target.txt").write_text("initial base\n", encoding="utf-8")
    git(repository, "add", "target.txt")
    git(repository, "commit", "-m", "initial base")
    return repository


class FakeParallelProvider:
    def __init__(
        self,
        name: str,
        *,
        conclusion: str = "ok",
        files_changed: tuple[str, ...] = (),
        commands: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.conclusion = conclusion
        self.files_changed = files_changed
        self.commands = commands
        self.started_runs: list[str] = []

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            sessions=True,
            resume=True,
            events=False,
            steer=False,
            cancel=True,
            tool_restrictions=False,
            display_name=self.name.capitalize(),
        )

    async def start(self, request: ProviderRequest) -> str:
        self.started_runs.append(request.run_id)
        return request.run_id

    async def result(self, run_id: str) -> NormalizedResult:
        await asyncio.sleep(0.01)
        return NormalizedResult(
            result_id=f"result-{run_id}",
            task_id="task-mock",
            run_id=run_id,
            base_revision=0,
            outcome=ProviderOutcome.COMPLETED,
            summary=f"{self.name} completed successfully",
            conclusion=self.conclusion,
            files_changed=self.files_changed,
            commands_run=self.commands,
        )

    async def cancel(self, run_id: str) -> None:
        pass

    async def steer(self, run_id: str, instruction: str) -> None:
        pass

    def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        raise NotImplementedError

    async def status(self, run_id: str) -> str:
        return "completed"

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        return request.run_id


@pytest.mark.asyncio
async def test_runtime_run_fanout_end_to_end(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    workspace_root = tmp_path / "workspace-state"

    prov_a = FakeParallelProvider("agent-a", conclusion="option A agreed")
    prov_b = FakeParallelProvider("agent-b", conclusion="option A agreed")

    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            worker_count=2,
            coding_repository_root=source,
            coding_workspace_root=workspace_root,
            coding_base_ref="HEAD",
        ),
        providers={"agent-a": prov_a, "agent-b": prov_b},
    )
    await runtime.start()

    synthesis = await runtime.run_fanout(
        "Research architecture tradeoffs for caching layer",
        providers=["agent-a", "agent-b"],
    )

    assert synthesis.consensus is SynthesisConsensus.FULL_AGREEMENT
    assert len(synthesis.candidates) == 2
    assert {c.provider for c in synthesis.candidates} == {"agent-a", "agent-b"}
    assert not synthesis.failures
    assert "Consensus: full_agreement." in synthesis.summary

    # Verify synthesis file was persisted on disk
    synthesis_file = tmp_path / "runtime" / "data" / "synthesis" / f"{synthesis.task_id}.json"
    assert synthesis_file.is_file()

    # Verify traces
    traces = await runtime.runtime_repository.traces(synthesis.task_id)
    phases = [t.phase for t in traces]
    assert "fanout.started" in phases
    assert "fanout.branch_started" in phases
    assert "fanout.branch_finished" in phases
    assert "synthesis.completed" in phases

    assert len(prov_a.started_runs) == 1
    assert len(prov_b.started_runs) == 1
    runs = await runtime.runtime_repository.list_runs(synthesis.task_id)
    coordinator = next(run for run in runs if run.provider == "fanout-coordinator")
    branches = [run for run in runs if run.provider != "fanout-coordinator"]
    assert coordinator.status is RunStatus.COMPLETED
    assert {run.status for run in branches} == {RunStatus.COMPLETED}
    task = await runtime.runtime_repository.get_task(synthesis.task_id)
    assert task is not None
    assert task.status is TaskStatus.COMPLETED

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_fanout_rejects_invalid_branch_sets(tmp_path: Path) -> None:
    provider = FakeParallelProvider("agent-a")
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        providers={"agent-a": provider},
    )
    await runtime.start()
    try:
        with pytest.raises(ValueError, match="at least one"):
            await runtime.run_fanout("Research something", providers=["agent-a"], max_branches=0)
        with pytest.raises(ValueError, match="unique"):
            await runtime.run_fanout(
                "Research something",
                providers=["agent-a", "agent-a"],
            )
        assert provider.started_runs == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_runtime_review_and_integrate_workflow(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    workspace_root = tmp_path / "workspace-state"

    prov = FakeParallelProvider("mock-provider")
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            worker_count=1,
            coding_repository_root=source,
            coding_workspace_root=workspace_root,
            coding_base_ref="HEAD",
        ),
        providers={"mock": prov},
    )
    await runtime.start()

    assert runtime.workspace_manager is not None
    # Allocate and mutate a workspace
    record = runtime.workspace_manager.allocate(
        source,
        workspace_id="ws-runtime-int",
        task_id="task-int",
        base_ref="HEAD",
        lease_owner="worker-int",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("updated in runtime\n", encoding="utf-8")

    # Review workspace
    conflict_report = runtime.review_workspace("ws-runtime-int")
    assert not conflict_report.has_conflicts

    # Validate workspace
    val_report = runtime.validate_workspace("ws-runtime-int", ["git status"])
    assert val_report.success

    # Integrate workspace
    await persist_operation_grant(
        runtime,
        "workspace.integrate:ws-runtime-int",
        grant_id="grant-runtime-integrate",
        actor_id="admin-user",
    )
    int_record = await runtime.integrate_workspace(
        "ws-runtime-int",
        grant_id="grant-runtime-integrate",
        device_id="device-local",
        commit_message="feat: runtime integrated edit",
    )
    assert (source / "target.txt").read_text("utf-8") == "updated in runtime\n"

    # Verify trace for integration
    traces = await runtime.runtime_repository.traces("task-int")
    phases = [t.phase for t in traces]
    assert "workspace.integrated" in phases

    # Rollback integration
    await persist_operation_grant(
        runtime,
        f"integration.rollback:{int_record.integration_id}",
        grant_id="grant-runtime-rollback",
        actor_id="admin-user",
    )
    await runtime.rollback_integration(
        int_record.integration_id,
        grant_id="grant-runtime-rollback",
        device_id="device-local",
    )
    assert (source / "target.txt").read_text("utf-8") == "initial base\n"

    # Verify rollback trace
    rollback_traces = await runtime.runtime_repository.traces(int_record.integration_id)
    assert any(t.phase == "workspace.rolled_back" for t in rollback_traces)

    await runtime.close()
