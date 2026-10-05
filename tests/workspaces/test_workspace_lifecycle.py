from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from sora.workspaces import (
    GitWorkspaceManager,
    WorkspaceError,
    WorkspaceLeaseError,
    WorkspaceStatus,
)


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


def test_list_and_status_tracking(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record_1 = manager.allocate(
        source,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    record_2 = manager.allocate(
        source,
        workspace_id="workspace-2",
        task_id="task-2",
        base_ref="HEAD",
        lease_owner="worker-2",
        lease_seconds=60,
    )

    workspaces = manager.list_workspaces()
    assert len(workspaces) == 2
    ids = {w.workspace_id for w in workspaces}
    assert ids == {"workspace-1", "workspace-2"}
    assert record_1.status is WorkspaceStatus.ACTIVE
    assert record_2.status is WorkspaceStatus.ACTIVE

    manager.release_lease("workspace-1", lease_owner="worker-1")
    reloaded_1 = manager.load("workspace-1")
    assert reloaded_1.status is WorkspaceStatus.RELEASED


def test_diff_workspace_and_diff_between_workspaces(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    rec_a = manager.allocate(
        source,
        workspace_id="workspace-a",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-a",
        lease_seconds=60,
    )
    rec_b = manager.allocate(
        source,
        workspace_id="workspace-b",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-b",
        lease_seconds=60,
    )

    (rec_a.worktree_path / "target.txt").write_text("option A\n", encoding="utf-8")
    (rec_b.worktree_path / "target.txt").write_text("option B\n", encoding="utf-8")

    diff_a = manager.diff_workspace("workspace-a")
    assert diff_a.changed_files == ("target.txt",)
    assert "+option A" in diff_a.diff

    diff_b = manager.diff_workspace("workspace-b")
    assert diff_b.changed_files == ("target.txt",)
    assert "+option B" in diff_b.diff

    inter_diff = manager.diff_between_workspaces("workspace-a", "workspace-b")
    assert "-option A" in inter_diff or "+option B" in inter_diff


def test_renew_lease_extends_deadline(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-renew",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=30,
    )
    original_expiry = record.lease_expires_at

    with pytest.raises(WorkspaceLeaseError):
        manager.renew_lease("workspace-renew", lease_owner="wrong-worker", extend_seconds=120)

    updated_lease = manager.renew_lease(
        "workspace-renew", lease_owner="worker-1", extend_seconds=120
    )
    assert updated_lease.expires_at > original_expiry
    reloaded = manager.load("workspace-renew")
    assert reloaded.lease_expires_at == updated_lease.expires_at


def test_recover_orphaned_workspace_snapshots_changes(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-orphan",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-crashed",
        lease_seconds=1,
    )
    # Writer made modifications and crashed without capturing artifact
    (record.worktree_path / "target.txt").write_text("crash edit\n", encoding="utf-8")
    (record.worktree_path / "untracked.txt").write_text("new file\n", encoding="utf-8")

    artifact, recovery_path = manager.recover_workspace(
        "workspace-orphan", reason="simulated_crash"
    )
    assert artifact.outcome == "recovered"
    assert "target.txt" in artifact.workspace.changed_files
    assert recovery_path.is_file()

    reloaded = manager.load("workspace-orphan")
    assert reloaded.status is WorkspaceStatus.RECOVERED
    # Lease should be unlinked/cleared
    assert not (manager.lease_root / "workspace-orphan.json").exists()


def test_discard_enforces_dirty_protection_and_path_containment(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-dirty",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("unsaved work\n", encoding="utf-8")
    (record.worktree_path / "only-copy.bin").write_bytes(b"\x00untracked recovery\xff")

    # Discarding a dirty workspace without force must fail closed
    with pytest.raises(WorkspaceError, match="Refusing to discard dirty workspace"):
        manager.discard("workspace-dirty", lease_owner="worker-1", force=False)

    # Forcing discard must snapshot recovery first so no data is lost
    manager.discard("workspace-dirty", lease_owner="worker-1", force=True)
    reloaded = manager.load("workspace-dirty")
    assert reloaded.status is WorkspaceStatus.DISCARDED
    assert not record.worktree_path.exists()
    # Ensure recovery snapshot was captured
    recovery_artifact = manager.artifact_root / "workspace-dirty" / "recovery.json"
    assert recovery_artifact.is_file()
    recovery_archive = manager.artifact_root / "workspace-dirty" / "untracked-files.zip"
    assert recovery_archive.is_file()
    with zipfile.ZipFile(recovery_archive) as archive:
        assert archive.read("only-copy.bin") == b"\x00untracked recovery\xff"


def test_cleanup_expired_workspaces(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-stale",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=1,
    )
    (record.worktree_path / "target.txt").write_text("stale content\n", encoding="utf-8")

    manager.release_lease("workspace-stale", lease_owner="worker-1")
    # max_age_seconds=0 cleans up immediately released workspaces
    cleaned = manager.cleanup_expired(max_age_seconds=0)
    assert "workspace-stale" in cleaned
    assert not record.worktree_path.exists()
    assert manager.load("workspace-stale").status is WorkspaceStatus.DISCARDED


def test_cleanup_never_discards_an_active_lease(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")

    record = manager.allocate(
        source,
        workspace_id="workspace-live",
        task_id="task-live",
        base_ref="HEAD",
        lease_owner="worker-live",
        lease_seconds=3600,
    )
    (record.worktree_path / "target.txt").write_text("live writer\n", encoding="utf-8")

    assert manager.cleanup_expired(max_age_seconds=0) == []
    assert record.worktree_path.is_dir()
    assert manager.load("workspace-live").status is WorkspaceStatus.ACTIVE
