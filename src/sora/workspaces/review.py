"""Review, validation, and authorized integration workflow for workspace artifacts."""

from __future__ import annotations

import os
import re
import subprocess
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from sora.contracts.base import NonEmptyText, StrictModel
from sora.security.operations import OperationAuthorization
from sora.workspaces.git import GitWorkspaceManager, WorkspaceError


class IntegrationStatus(StrEnum):
    """Lifecycle status of a workspace integration proposal."""

    PENDING_REVIEW = "pending_review"
    VALIDATED = "validated"
    INTEGRATED = "integrated"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class IntegrationError(WorkspaceError):
    """Base error for review and integration failures."""


class IntegrationConflictError(IntegrationError):
    """Proposed changes conflict with the target branch or checkout state."""


class IntegrationAuthorizationError(IntegrationError):
    """Integration was requested without required explicit authorization."""


class IntegrationValidationError(IntegrationError):
    """Pre-integration validation commands failed."""


class ConflictReport(StrictModel):
    """Detailed report of conflict inspection against target repository state."""

    has_conflicts: bool
    conflicting_files: tuple[str, ...] = ()
    base_commit: NonEmptyText
    target_head_commit: NonEmptyText
    details: str = ""


class ValidationReport(StrictModel):
    """Result of pre-integration automated test and check execution."""

    success: bool
    commands_run: tuple[str, ...] = ()
    output: str = ""
    errors: tuple[str, ...] = ()


class IntegrationRecord(StrictModel):
    """Durable, attributable record of an authorized merge with rollback instructions."""

    integration_id: str
    workspace_id: str
    task_id: str
    run_id: str
    target_repository: Path
    base_commit: NonEmptyText
    integrated_commit: NonEmptyText
    applied_diff: str
    authorized_by: NonEmptyText
    authorization_grant_id: str | None = None
    authorization_approval_id: str | None = None
    rollback_instructions: str
    integrated_at: datetime
    status: IntegrationStatus = IntegrationStatus.INTEGRATED
    rollback_authorized_by: str | None = None
    rollback_grant_id: str | None = None


class ReviewManager:
    """Manage diff review, conflict checks, validation, and authorized merge."""

    def __init__(self, workspace_manager: GitWorkspaceManager) -> None:
        self.workspace_manager = workspace_manager
        self.integration_root = self.workspace_manager.state_root / "integrations"
        self.integration_root.mkdir(parents=True, exist_ok=True)

    def check_conflicts(
        self,
        workspace_id: str,
        *,
        target_ref: str = "HEAD",
    ) -> ConflictReport:
        """Check whether workspace diff applies cleanly to the target repository ref."""
        record = self.workspace_manager.load(workspace_id)
        target_root = record.repository_root
        target_head = self._git(target_root, "rev-parse", target_ref).strip()
        base_commit = record.base_commit

        artifact = self.workspace_manager.diff_workspace(workspace_id, target_ref=base_commit)
        if not artifact.diff.strip() and not artifact.changed_files:
            return ConflictReport(
                has_conflicts=False,
                conflicting_files=(),
                base_commit=base_commit,
                target_head_commit=target_head,
                details="No changes detected in workspace.",
            )

        # Check if patch applies cleanly to target repository
        check_proc = subprocess.run(
            ["git", "apply", "--check", "--ignore-space-change", "--binary", "-"],
            cwd=target_root,
            input=artifact.diff,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if check_proc.returncode == 0:
            return ConflictReport(
                has_conflicts=False,
                conflicting_files=(),
                base_commit=base_commit,
                target_head_commit=target_head,
                details="Patch applies cleanly without conflicts.",
            )

        # Parse conflicting files from stderr
        conflicting: list[str] = []
        for line in check_proc.stderr.splitlines():
            pattern = r"error: (?:patch failed: |cannot apply binary patch to )([^\s:]+)"
            match = re.search(pattern, line)
            if match:
                conflicting.append(match.group(1))
            elif "does not exist in index" in line or "already exists in index" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    conflicting.append(parts[1].strip())

        if not conflicting:
            conflicting = list(artifact.changed_files)

        return ConflictReport(
            has_conflicts=True,
            conflicting_files=tuple(sorted(set(conflicting))),
            base_commit=base_commit,
            target_head_commit=target_head,
            details=check_proc.stderr.strip() or "Git apply --check failed with conflicts.",
        )

    def validate(
        self,
        workspace_id: str,
        validation_commands: Sequence[str],
    ) -> ValidationReport:
        """Execute validation commands inside the isolated workspace before integration."""
        if not validation_commands:
            return ValidationReport(
                success=True,
                commands_run=(),
                output="No validation commands required.",
            )

        record = self.workspace_manager.load(workspace_id)
        outputs: list[str] = []
        errors: list[str] = []

        for command in validation_commands:
            proc = subprocess.run(
                command,
                cwd=record.worktree_path,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out = proc.stdout.strip()
            err = proc.stderr.strip()
            if out:
                outputs.append(f"[{command}] {out}")
            if proc.returncode != 0:
                err_msg = (
                    f"Command '{command}' failed with exit code {proc.returncode}: {err or out}"
                )
                errors.append(err_msg)
                return ValidationReport(
                    success=False,
                    commands_run=tuple(validation_commands),
                    output="\n".join(outputs),
                    errors=tuple(errors),
                )

        return ValidationReport(
            success=True,
            commands_run=tuple(validation_commands),
            output="\n".join(outputs),
            errors=(),
        )

    def integrate(
        self,
        workspace_id: str,
        *,
        authorization: OperationAuthorization,
        commit_message: str | None = None,
        validation_commands: Sequence[str] = (),
    ) -> IntegrationRecord:
        """Atomically integrate authorized workspace changes into the target repository.

        Enforces:
        1. Exact persisted operation grant and approved actor evidence.
        2. Clean conflict check.
        3. Pre-integration validation commands pass.
        4. Target repository uncommitted changes are preserved and not clobbered.
        5. Detailed rollback documentation.
        """
        try:
            authorization.require_scope(f"workspace.integrate:{workspace_id}")
        except PermissionError as exc:
            raise IntegrationAuthorizationError(str(exc)) from exc
        auth_actor = authorization.authorized_by
        grant_id = authorization.grant.grant_id
        approval_id = authorization.approval.approval_id

        conflicts = self.check_conflicts(workspace_id)
        if conflicts.has_conflicts:
            raise IntegrationConflictError(
                f"Cannot integrate workspace '{workspace_id}': conflicts detected in "
                f"{conflicts.conflicting_files}. Details: {conflicts.details}"
            )

        if validation_commands:
            val = self.validate(workspace_id, validation_commands)
            if not val.success:
                raise IntegrationValidationError(f"Pre-integration validation failed: {val.errors}")

        record = self.workspace_manager.load(workspace_id)
        target_root = record.repository_root
        artifact = self.workspace_manager.diff_workspace(
            workspace_id,
            target_ref=record.base_commit,
        )
        if not artifact.diff.strip():
            raise IntegrationError(f"Workspace '{workspace_id}' has no tracked diff to integrate.")

        # Check target repository dirty status to avoid clobbering untracked user files
        status_raw = self._git(target_root, "status", "--porcelain=v1", "--untracked-files=all")
        dirty_target_files = {
            line[3:].strip()
            for line in status_raw.splitlines()
            if len(line) > 3 and line[3:].strip()
        }
        overlapping = dirty_target_files.intersection(set(artifact.changed_files))
        if overlapping:
            raise IntegrationConflictError(
                f"Cannot integrate workspace '{workspace_id}': target repository has "
                f"uncommitted user changes in overlapping files: {sorted(overlapping)}"
            )

        if self._has_staged_changes(target_root):
            raise IntegrationConflictError(
                "Cannot integrate while the target repository has pre-existing staged changes."
            )

        # git apply --index updates the worktree and index as one checked operation.
        original_head = self._git(target_root, "rev-parse", "HEAD").strip()
        try:
            apply_proc = subprocess.run(
                ["git", "apply", "--binary", "--ignore-space-change", "--index", "-"],
                cwd=target_root,
                input=artifact.diff,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if apply_proc.returncode != 0:
                raise IntegrationError(f"Failed to apply patch: {apply_proc.stderr}")

            msg = commit_message or (
                f"SORA integrate workspace {workspace_id} (authorized by {auth_actor})"
            )
            self._git(target_root, "commit", "-m", msg)
            integrated_commit = self._git(target_root, "rev-parse", "HEAD").strip()
        except Exception as exc:
            self._restore_paths(target_root, original_head, artifact.changed_files)
            if isinstance(exc, IntegrationError):
                raise
            raise IntegrationError(f"Integration failed and was rolled back: {exc}") from exc

        integration_id = f"int-{workspace_id}-{uuid.uuid4().hex[:8]}"
        rollback_instructions = f"git revert --no-edit {integrated_commit}"

        int_record = IntegrationRecord(
            integration_id=integration_id,
            workspace_id=workspace_id,
            task_id=record.task_id,
            run_id=record.workspace_id.removeprefix("workspace-"),
            target_repository=target_root,
            base_commit=record.base_commit,
            integrated_commit=integrated_commit,
            applied_diff=artifact.diff,
            authorized_by=auth_actor,
            authorization_grant_id=grant_id,
            authorization_approval_id=approval_id,
            rollback_instructions=rollback_instructions,
            integrated_at=datetime.now(UTC),
            status=IntegrationStatus.INTEGRATED,
        )

        record_file = self.integration_root / f"{integration_id}.json"
        try:
            self._write_record(record_file, int_record)
        except Exception:
            # A merge without its durable authorization record is not a valid integration.
            self._git(target_root, "revert", "--no-edit", integrated_commit)
            raise
        return int_record

    def rollback(
        self,
        integration_id: str,
        *,
        authorization: OperationAuthorization,
    ) -> None:
        """Roll back an integrated commit using recorded rollback instructions."""
        try:
            authorization.require_scope(f"integration.rollback:{integration_id}")
        except PermissionError as exc:
            raise IntegrationAuthorizationError(str(exc)) from exc
        auth_actor = authorization.authorized_by
        grant_id = authorization.grant.grant_id

        record_file = self.integration_root / f"{integration_id}.json"
        if not record_file.is_file():
            raise IntegrationError(f"Unknown integration ID: {integration_id}")

        int_record = IntegrationRecord.model_validate_json(record_file.read_text("utf-8"))
        if int_record.status is IntegrationStatus.ROLLED_BACK:
            raise IntegrationError(f"Integration '{integration_id}' is already rolled back.")

        self._git(int_record.target_repository, "revert", "--no-edit", int_record.integrated_commit)

        updated = int_record.model_copy(
            update={
                "status": IntegrationStatus.ROLLED_BACK,
                "rollback_authorized_by": auth_actor,
                "rollback_grant_id": grant_id,
            }
        )
        self._write_record(record_file, updated)

    @staticmethod
    def _has_staged_changes(cwd: Path) -> bool:
        completed = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--exit-code"],
            cwd=cwd,
            capture_output=True,
            check=False,
        )
        if completed.returncode not in (0, 1):
            raise IntegrationError("Could not inspect the target Git index")
        return completed.returncode == 1

    @staticmethod
    def _restore_paths(cwd: Path, source_ref: str, files: Sequence[str]) -> None:
        if not files:
            return
        completed = subprocess.run(
            ["git", "restore", f"--source={source_ref}", "--staged", "--worktree", "--", *files],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise IntegrationError(f"Failed to restore target after integration error: {detail}")

    @staticmethod
    def _write_record(path: Path, record: IntegrationRecord) -> None:
        temporary = path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)

    @staticmethod
    def _git(cwd: Path, *args: str) -> str:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "unknown Git error"
            raise IntegrationError(f"git {' '.join(args[:2])} failed: {detail}")
        return completed.stdout
