"""Initial Git worktree isolation for single-writer coding tasks."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sora.contracts.base import NonEmptyText, StrictModel
from sora.contracts.models import NormalizedResult

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class WorkspaceError(RuntimeError):
    """Workspace allocation or inspection failed safely."""


class WorkspaceLeaseError(WorkspaceError):
    """A writer does not own the required live workspace lease."""


class WorkspaceRecord(StrictModel):
    """Durable identity and source-state record for one owned worktree."""

    workspace_id: str
    task_id: str
    repository_root: Path
    worktree_path: Path
    requested_base_ref: NonEmptyText
    base_commit: NonEmptyText
    source_dirty_before: tuple[str, ...] = ()
    lease_owner: NonEmptyText
    lease_expires_at: datetime
    created_at: datetime


class CodingArtifact(StrictModel):
    """Reviewable Git evidence captured without staging or merging changes."""

    workspace_id: str
    requested_base_ref: NonEmptyText
    base_commit: NonEmptyText
    head_commit: NonEmptyText
    status: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    diff: str = ""
    captured_at: datetime
    warnings: tuple[str, ...] = ()


class CodingRunArtifact(StrictModel):
    """Workspace evidence joined to the attributable normalized provider result."""

    workspace: CodingArtifact
    provider: NonEmptyText
    result_id: str | None = None
    outcome: str | None = None
    commands_run: tuple[str, ...] = ()
    verification_commands: tuple[str, ...] = ()
    files_read: tuple[str, ...] = ()
    files_changed: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class _LeaseRecord(StrictModel):
    workspace_id: str
    lease_owner: NonEmptyText
    acquired_at: datetime
    expires_at: datetime


class GitWorkspaceManager:
    """Allocate durable, leased worktrees beneath one explicitly owned state root.

    This is the P05 single-writer boundary. Lifecycle operations that can discard a
    worktree deliberately remain for P07, so this manager never removes a workspace
    after it has been handed to a coding provider.
    """

    def __init__(self, state_root: str | Path) -> None:
        self.state_root = Path(state_root).resolve()
        self.worktree_root = self.state_root / "worktrees"
        self.record_root = self.state_root / "records"
        self.lease_root = self.state_root / "leases"
        self.artifact_root = self.state_root / "artifacts"
        for path in (
            self.worktree_root,
            self.record_root,
            self.lease_root,
            self.artifact_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def allocate(
        self,
        repository: str | Path,
        *,
        workspace_id: str,
        task_id: str,
        base_ref: str,
        lease_owner: str,
        lease_seconds: float = 900,
    ) -> WorkspaceRecord:
        """Allocate or idempotently reopen an owned detached worktree."""
        self._validate_identifier(workspace_id, "workspace_id")
        self._validate_identifier(task_id, "task_id")
        self._validate_identifier(lease_owner, "lease_owner")
        if not base_ref.strip() or base_ref.startswith("-"):
            raise WorkspaceError("base_ref must be explicit and cannot begin with '-'")
        if lease_seconds <= 0:
            raise WorkspaceError("lease_seconds must be positive")

        repository_root = self._repository_root(repository)
        base_commit = self._git(
            repository_root,
            "rev-parse",
            "--verify",
            f"{base_ref}^{{commit}}",
        ).strip()
        record_path = self._record_path(workspace_id)
        worktree_path = (self.worktree_root / workspace_id).resolve()
        self._require_beneath(worktree_path, self.worktree_root)

        if record_path.exists():
            existing = WorkspaceRecord.model_validate_json(record_path.read_text("utf-8"))
            if (
                existing.repository_root != repository_root
                or existing.worktree_path != worktree_path
                or existing.task_id != task_id
                or existing.requested_base_ref != base_ref
                or existing.base_commit != base_commit
            ):
                raise WorkspaceError("workspace_id already belongs to a different allocation")
            lease = self._acquire_lease(
                workspace_id,
                lease_owner=lease_owner,
                lease_seconds=lease_seconds,
            )
            reopened = existing.model_copy(
                update={
                    "lease_owner": lease.lease_owner,
                    "lease_expires_at": lease.expires_at,
                }
            )
            self._write_json(record_path, reopened.model_dump(mode="json"))
            return reopened

        if worktree_path.exists():
            raise WorkspaceError("refusing to adopt an unrecorded workspace path")

        lease = self._acquire_lease(
            workspace_id,
            lease_owner=lease_owner,
            lease_seconds=lease_seconds,
        )
        dirty_before = tuple(
            self._git(
                repository_root,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ).splitlines()
        )
        try:
            self._git(
                repository_root,
                "worktree",
                "add",
                "--detach",
                str(worktree_path),
                base_commit,
            )
        except Exception:
            self._release_lease_file(workspace_id, lease_owner)
            raise

        record = WorkspaceRecord(
            workspace_id=workspace_id,
            task_id=task_id,
            repository_root=repository_root,
            worktree_path=worktree_path,
            requested_base_ref=base_ref,
            base_commit=base_commit,
            source_dirty_before=dirty_before,
            lease_owner=lease.lease_owner,
            lease_expires_at=lease.expires_at,
            created_at=lease.acquired_at,
        )
        try:
            self._write_json(record_path, record.model_dump(mode="json"))
        except Exception:
            # Allocation has not escaped to a provider yet, so this rollback cannot
            # discard provider or user edits.
            self._git(repository_root, "worktree", "remove", "--force", str(worktree_path))
            self._release_lease_file(workspace_id, lease_owner)
            raise
        return record

    def load(self, workspace_id: str) -> WorkspaceRecord:
        self._validate_identifier(workspace_id, "workspace_id")
        path = self._record_path(workspace_id)
        if not path.is_file():
            raise WorkspaceError(f"unknown workspace: {workspace_id}")
        return WorkspaceRecord.model_validate_json(path.read_text("utf-8"))

    def assert_write_lease(self, workspace_id: str, lease_owner: str) -> None:
        """Fail closed unless the caller owns a non-expired lease."""
        lease = self._load_lease(workspace_id)
        if lease.lease_owner != lease_owner:
            raise WorkspaceLeaseError("workspace lease belongs to another writer")
        if lease.expires_at <= datetime.now(UTC):
            raise WorkspaceLeaseError("workspace write lease has expired")

    def capture_artifact(self, workspace_id: str, *, lease_owner: str) -> CodingArtifact:
        """Capture review evidence without staging, committing, or merging."""
        self.assert_write_lease(workspace_id, lease_owner)
        record = self.load(workspace_id)
        status = tuple(
            self._git(
                record.worktree_path,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ).splitlines()
        )
        changed_files = tuple(
            line[3:] for line in status if len(line) > 3 and line[3:].strip()
        )
        tracked_diff = self._git(
            record.worktree_path,
            "diff",
            "--binary",
            "--no-ext-diff",
            record.base_commit,
            "--",
        )
        warnings = (
            ("Untracked files are listed in status but are not embedded in the Git diff.",)
            if any(line.startswith("?? ") for line in status)
            else ()
        )
        return CodingArtifact(
            workspace_id=workspace_id,
            requested_base_ref=record.requested_base_ref,
            base_commit=record.base_commit,
            head_commit=self._git(record.worktree_path, "rev-parse", "HEAD").strip(),
            status=status,
            changed_files=changed_files,
            diff=tracked_diff,
            captured_at=datetime.now(UTC),
            warnings=warnings,
        )

    def release_lease(self, workspace_id: str, *, lease_owner: str) -> None:
        """Release only the caller's lease; retain the worktree and all artifacts."""
        lease = self._load_lease(workspace_id)
        if lease.lease_owner != lease_owner:
            raise WorkspaceLeaseError("workspace lease belongs to another writer")
        self._release_lease_file(workspace_id, lease_owner)

    def capture_run_artifact(
        self,
        workspace_id: str,
        *,
        lease_owner: str,
        provider: str,
        result: NormalizedResult | None,
    ) -> tuple[CodingRunArtifact, Path]:
        """Persist a review artifact before releasing write authority."""
        workspace = self.capture_artifact(workspace_id, lease_owner=lease_owner)
        commands = result.commands_run if result is not None else ()
        verification_commands = tuple(
            command
            for command in commands
            if re.search(r"(?:pytest|mypy|ruff|verify|test|compileall)", command, re.IGNORECASE)
        )
        missing_result_warning = (
            ("Provider result was unavailable; workspace evidence was retained.",)
            if result is None
            else ()
        )
        artifact = CodingRunArtifact(
            workspace=workspace,
            provider=provider,
            result_id=result.result_id if result is not None else None,
            outcome=result.outcome.value if result is not None else None,
            commands_run=commands,
            verification_commands=verification_commands,
            files_read=result.files_read if result is not None else (),
            files_changed=result.files_changed if result is not None else (),
            uncertainties=result.uncertainties if result is not None else (),
            warnings=(result.warnings if result is not None else ()) + missing_result_warning,
        )
        destination = (self.artifact_root / workspace_id / "coding-run.json").resolve()
        self._require_beneath(destination, self.artifact_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._write_json(destination, artifact.model_dump(mode="json"))
        return artifact, destination

    def _acquire_lease(
        self,
        workspace_id: str,
        *,
        lease_owner: str,
        lease_seconds: float,
    ) -> _LeaseRecord:
        path = self._lease_path(workspace_id)
        if path.exists():
            existing = self._load_lease(workspace_id)
            if existing.expires_at > datetime.now(UTC):
                if existing.lease_owner != lease_owner:
                    raise WorkspaceLeaseError("workspace already has a live writer")
                return existing
            try:
                path.unlink()
            except FileNotFoundError:
                pass

        acquired_at = datetime.now(UTC)
        lease = _LeaseRecord(
            workspace_id=workspace_id,
            lease_owner=lease_owner,
            acquired_at=acquired_at,
            expires_at=acquired_at + timedelta(seconds=lease_seconds),
        )
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError as exc:
            raise WorkspaceLeaseError("workspace lease was acquired concurrently") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(lease.model_dump(mode="json"), handle, indent=2)
            handle.write("\n")
        return lease

    def _load_lease(self, workspace_id: str) -> _LeaseRecord:
        path = self._lease_path(workspace_id)
        if not path.is_file():
            raise WorkspaceLeaseError("workspace has no write lease")
        return _LeaseRecord.model_validate_json(path.read_text("utf-8"))

    def _release_lease_file(self, workspace_id: str, lease_owner: str) -> None:
        path = self._lease_path(workspace_id)
        if not path.exists():
            return
        lease = self._load_lease(workspace_id)
        if lease.lease_owner != lease_owner:
            raise WorkspaceLeaseError("workspace lease belongs to another writer")
        path.unlink()

    def _record_path(self, workspace_id: str) -> Path:
        return self.record_root / f"{workspace_id}.json"

    def _lease_path(self, workspace_id: str) -> Path:
        return self.lease_root / f"{workspace_id}.json"

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> None:
        if not _SAFE_ID.fullmatch(value):
            raise WorkspaceError(f"{field_name} contains unsafe characters")

    @staticmethod
    def _require_beneath(path: Path, parent: Path) -> None:
        if not path.is_relative_to(parent.resolve()):
            raise WorkspaceError("workspace path escaped the configured state root")

    def _repository_root(self, repository: str | Path) -> Path:
        candidate = Path(repository).resolve()
        if not candidate.is_dir():
            raise WorkspaceError("repository path must be an existing directory")
        return Path(self._git(candidate, "rev-parse", "--show-toplevel").strip()).resolve()

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
            raise WorkspaceError(f"git {' '.join(args[:2])} failed: {detail}")
        return completed.stdout

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(f".tmp-{os.getpid()}")
        temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
