from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

from sora.workspaces import (
    GitWorkspaceManager,
    IntegrationAuthorizationError,
    IntegrationError,
    IntegrationStatus,
    IntegrationValidationError,
    ReviewManager,
)
from tests.authorization_helpers import make_operation_authorization


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
    (repository / "target.txt").write_text("line 1\nline 2\n", encoding="utf-8")
    git(repository, "add", "target.txt")
    git(repository, "commit", "-m", "initial base")
    return repository


def test_conflict_detection(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)

    record = manager.allocate(
        source,
        workspace_id="ws-conflict",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("line 1\nworkspace edit\n", encoding="utf-8")

    # Before target moves: should have no conflicts
    report_clean = review_mgr.check_conflicts("ws-conflict")
    assert not report_clean.has_conflicts

    # Target repository commits a conflicting change
    (source / "target.txt").write_text("line 1\nconflicting main edit\n", encoding="utf-8")
    git(source, "add", "target.txt")
    git(source, "commit", "-m", "concurrent conflicting commit")

    # Now check conflicts: should detect conflict in target.txt
    report_conflict = review_mgr.check_conflicts("ws-conflict")
    assert report_conflict.has_conflicts
    assert "target.txt" in report_conflict.conflicting_files


def test_validation_workflow(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)

    _ = manager.allocate(
        source,
        workspace_id="ws-val",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )

    # Validation succeeds
    report_pass = review_mgr.validate("ws-val", ["git status"])
    assert report_pass.success

    # Validation fails
    report_fail = review_mgr.validate("ws-val", ["git nonexistent-command-xyz"])
    assert not report_fail.success
    assert len(report_fail.errors) > 0


def test_integration_authorization_and_safety_checks(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)

    record = manager.allocate(
        source,
        workspace_id="ws-auth",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("line 1\nnew line 2\n", encoding="utf-8")

    # Caller-asserted identity is never an authorization input.
    assert "authorized_by" not in inspect.signature(review_mgr.integrate).parameters
    assert "authorized_by" not in inspect.signature(review_mgr.rollback).parameters

    # A valid grant for a different operation must fail closed.
    wrong_scope = make_operation_authorization("workspace.integrate:somewhere-else")
    with pytest.raises(IntegrationAuthorizationError, match="scoped"):
        review_mgr.integrate("ws-auth", authorization=wrong_scope)

    # Pre-integration validation failure aborts integration
    authorization = make_operation_authorization("workspace.integrate:ws-auth")
    with pytest.raises(IntegrationValidationError):
        review_mgr.integrate(
            "ws-auth",
            authorization=authorization,
            validation_commands=["python -c 'raise SystemExit(1)'"],
        )


def test_atomic_integration_and_rollback(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    # Add an unrelated dirty file in user checkout that must be preserved
    (source / "notes.txt").write_text("my uncommitted notes\n", encoding="utf-8")

    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)

    record = manager.allocate(
        source,
        workspace_id="ws-integrate",
        task_id="task-int",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("integrated content\n", encoding="utf-8")

    # Perform authorized integration
    int_record = review_mgr.integrate(
        "ws-integrate",
        authorization=make_operation_authorization("workspace.integrate:ws-integrate"),
        commit_message="feat: apply tested workspace edit",
    )

    assert int_record.status is IntegrationStatus.INTEGRATED
    assert (source / "target.txt").read_text("utf-8") == "integrated content\n"
    # Verify unrelated user notes were preserved
    assert (source / "notes.txt").read_text("utf-8") == "my uncommitted notes\n"
    assert "git revert" in int_record.rollback_instructions

    # Roll back integration
    review_mgr.rollback(
        int_record.integration_id,
        authorization=make_operation_authorization(
            f"integration.rollback:{int_record.integration_id}",
            grant_id="grant-rollback",
        ),
    )
    assert (source / "target.txt").read_text("utf-8") == "line 1\nline 2\n"
    assert (source / "notes.txt").read_text("utf-8") == "my uncommitted notes\n"


def test_commit_failure_restores_only_integration_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = committed_repository(tmp_path)
    (source / "notes.txt").write_text("preserve me\n", encoding="utf-8")
    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)
    record = manager.allocate(
        source,
        workspace_id="ws-failed-commit",
        task_id="task-int",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    (record.worktree_path / "target.txt").write_text("candidate\n", encoding="utf-8")

    original_git = review_mgr._git

    def fail_commit(cwd: Path, *args: str) -> str:
        if args and args[0] == "commit":
            raise IntegrationError("simulated commit failure")
        return original_git(cwd, *args)

    monkeypatch.setattr(review_mgr, "_git", fail_commit)
    with pytest.raises(IntegrationError, match="simulated commit failure"):
        review_mgr.integrate(
            "ws-failed-commit",
            authorization=make_operation_authorization("workspace.integrate:ws-failed-commit"),
        )

    assert (source / "target.txt").read_text("utf-8") == "line 1\nline 2\n"
    assert (source / "notes.txt").read_text("utf-8") == "preserve me\n"
    assert git(source, "diff", "--cached") == ""


def test_noop_integration_cannot_create_a_revert_target(tmp_path: Path) -> None:
    source = committed_repository(tmp_path)
    original_head = git(source, "rev-parse", "HEAD").strip()
    manager = GitWorkspaceManager(tmp_path / "state")
    review_mgr = ReviewManager(manager)
    manager.allocate(
        source,
        workspace_id="ws-noop",
        task_id="task-noop",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )

    with pytest.raises(IntegrationError, match="no tracked diff"):
        review_mgr.integrate(
            "ws-noop",
            authorization=make_operation_authorization("workspace.integrate:ws-noop"),
        )
    assert git(source, "rev-parse", "HEAD").strip() == original_head
    assert list(review_mgr.integration_root.glob("*.json")) == []
