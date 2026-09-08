from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from sora.contracts.models import NormalizedResult, ProviderOutcome
from sora.workspaces import GitWorkspaceManager, WorkspaceLeaseError


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
    (repository / "target.txt").write_text("before\n", encoding="utf-8")
    git(repository, "add", "target.txt")
    git(repository, "commit", "-m", "fixture base")
    return repository


def test_owned_worktree_preserves_dirty_source_and_produces_review_artifact(
    tmp_path: Path,
) -> None:
    source = committed_repository(tmp_path)
    (source / "user-notes.txt").write_text("preserve me\n", encoding="utf-8")
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )

    assert record.worktree_path != source
    assert "?? user-notes.txt" in record.source_dirty_before
    assert (record.worktree_path / "target.txt").read_text("utf-8") == "before\n"
    (record.worktree_path / "target.txt").write_text("after\n", encoding="utf-8")

    artifact = manager.capture_artifact("workspace-1", lease_owner="worker-1")
    assert artifact.base_commit == record.base_commit
    assert artifact.head_commit == record.base_commit
    assert artifact.changed_files == ("target.txt",)
    assert "-before" in artifact.diff
    assert "+after" in artifact.diff
    assert (source / "target.txt").read_text("utf-8") == "before\n"
    assert (source / "user-notes.txt").read_text("utf-8") == "preserve me\n"


def test_only_lease_owner_can_reopen_capture_or_release(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")
    first = manager.allocate(
        source,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )

    reopened = manager.allocate(
        source,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    assert reopened.worktree_path == first.worktree_path
    with pytest.raises(WorkspaceLeaseError, match="live writer"):
        manager.allocate(
            source,
            workspace_id="workspace-1",
            task_id="task-1",
            base_ref="HEAD",
            lease_owner="worker-2",
            lease_seconds=60,
        )
    with pytest.raises(WorkspaceLeaseError, match="another writer"):
        manager.capture_artifact("workspace-1", lease_owner="worker-2")
    with pytest.raises(WorkspaceLeaseError, match="another writer"):
        manager.release_lease("workspace-1", lease_owner="worker-2")

    manager.release_lease("workspace-1", lease_owner="worker-1")
    with pytest.raises(WorkspaceLeaseError, match="no write lease"):
        manager.assert_write_lease("workspace-1", "worker-1")


def test_run_artifact_joins_result_evidence_and_is_persisted(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")
    record = manager.allocate(
        source,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("after\n", encoding="utf-8")
    result = NormalizedResult(
        result_id="result-1",
        task_id="task-1",
        run_id="run-1",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="changed",
        conclusion="changed",
        commands_run=("python -m pytest -q",),
        files_changed=("target.txt",),
    )

    artifact, path = manager.capture_run_artifact(
        "workspace-1",
        lease_owner="worker-1",
        provider="codex-app-server",
        result=result,
    )

    assert artifact.result_id == "result-1"
    assert artifact.verification_commands == ("python -m pytest -q",)
    assert artifact.workspace.changed_files == ("target.txt",)
    assert path.is_file()
    assert '"base_commit"' in path.read_text("utf-8")
