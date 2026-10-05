"""Owner-local declared projects and atomic writer-root evidence in the Core database."""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sora.persistence.database import SQLiteDatabase
from sora.providers.windows_job import job_name, process_may_be_alive, writer_job_empty


def project_directory(raw: str) -> Path:
    if not raw or len(raw) > 4096 or raw.startswith(("\\\\", "//")):
        raise ValueError("Select an absolute local project directory")
    path = Path(raw)
    if not path.is_absolute():
        raise ValueError("Select an absolute local project directory")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise ValueError("Selected project directory is missing or unreadable") from exc
    if not resolved.is_dir() or resolved == Path(resolved.anchor) or resolved == Path.home():
        raise ValueError("Select a project folder, not a drive or account root")
    return resolved


def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def overlapping(first: str, second: str) -> bool:
    left, right = Path(first), Path(second)
    return left == right or left in right.parents or right in left.parents


@dataclass(frozen=True)
class PathSnapshot:
    root: Path
    files: dict[str, tuple[int, int]]
    complete: bool


def snapshot(root: Path, *, limit: int = 10000, seconds: float = 2) -> PathSnapshot:
    """Bounded metadata only; no content, symlink traversal or authoritative read audit."""
    files: dict[str, tuple[int, int]] = {}
    pending = [root]
    deadline = time.monotonic() + seconds
    complete = True
    while pending:
        if len(files) >= limit or time.monotonic() >= deadline:
            return PathSnapshot(root, files, False)
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if len(files) >= limit or time.monotonic() >= deadline:
                        return PathSnapshot(root, files, False)
                    if entry.is_symlink() or entry.name == ".git":
                        continue
                    # Windows directory junctions are reparse points, not always symlinks.
                    info = entry.stat(follow_symlinks=False)
                    if getattr(info, "st_file_attributes", 0) & 0x400:
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        pending.append(Path(entry.path))
                    elif entry.is_file(follow_symlinks=False):
                        files[entry.path] = (info.st_size, info.st_mtime_ns)
        except OSError:
            complete = False
    return PathSnapshot(root, files, complete)


class ProjectPaths:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    @staticmethod
    def _event(
        db: sqlite3.Connection,
        run_id: str,
        root: str,
        operation: str,
        status: str,
        source: str = "core_observed",
    ) -> None:
        db.execute(
            "INSERT INTO path_events VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                run_id,
                root,
                operation,
                status,
                source,
                datetime.now(UTC).isoformat(),
            ),
        )

    async def acquire(self, run_id: str, task_id: str, root: Path) -> bool:
        canonical = path_key(root)

        def write(db: sqlite3.Connection) -> bool:
            for row in db.execute("SELECT run_id, canonical_root FROM path_leases"):
                if row["run_id"] == run_id:
                    return bool(row["canonical_root"] == canonical)
                if overlapping(canonical, row["canonical_root"]):
                    self._event(db, run_id, str(root), "write.reserve", "conflict")
                    return False
            db.execute(
                "INSERT INTO path_leases VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    task_id,
                    canonical,
                    str(root),
                    job_name(run_id),
                    "reserved",
                    datetime.now(UTC).isoformat(),
                    os.getpid(),
                ),
            )
            self._event(db, run_id, str(root), "write.reserve", "reserved", "declared_root")
            return True

        return await self.database.write(write)

    def authorized(self, run_id: str, root: str) -> bool:
        """Adapter pre-launch check; each lookup uses its own bounded SQLite connection."""
        with sqlite3.connect(self.database.path, timeout=5) as db:
            row = db.execute(
                "SELECT canonical_root, status FROM path_leases WHERE run_id=?",
                (run_id,),
            ).fetchone()
        return bool(row and row[0] == path_key(Path(root)) and row[1] == "reserved")

    async def settle(self, run_id: str, *, stopped: bool) -> None:
        def write(db: sqlite3.Connection) -> None:
            row = db.execute("SELECT display_root FROM path_leases WHERE run_id=?", (run_id,))
            found = row.fetchone()
            if found is None:
                return
            if stopped:
                db.execute("DELETE FROM path_leases WHERE run_id=?", (run_id,))
            else:
                db.execute("UPDATE path_leases SET status='uncertain' WHERE run_id=?", (run_id,))
            self._event(
                db,
                run_id,
                found[0],
                "write.release",
                "stopped" if stopped else "uncertain",
            )

        await self.database.write(write)

    async def reconcile(self) -> None:
        import asyncio

        rows = await self.database.read(
            lambda db: [
                dict(row)
                for row in db.execute(
                    "SELECT p.run_id, p.job_name, p.owner_pid, r.status FROM path_leases p "
                    "JOIN agent_runs r ON r.run_id=p.run_id",
                )
            ]
        )
        for row in rows:
            try:
                if await asyncio.to_thread(process_may_be_alive, row["owner_pid"]) and (
                    row["owner_pid"] != os.getpid()
                    or row["status"] in {"pending", "launching", "running", "cancel_requested"}
                ):
                    continue
                stopped = await asyncio.to_thread(writer_job_empty, row["job_name"])
            except OSError:
                stopped = False
            await self.settle(row["run_id"], stopped=stopped)

    async def record(self, run_id: str, path: str, operation: str, source: str) -> None:
        await self.database.write(
            lambda db: self._event(
                db,
                run_id,
                path,
                operation,
                "reported" if source == "provider_reported" else "observed",
                source,
            )
        )

    async def record_diff(self, run_id: str, before: PathSnapshot) -> None:
        import asyncio

        after = await asyncio.to_thread(snapshot, before.root)
        if not (before.complete and after.complete):
            await self.record(run_id, str(before.root), "diff.incomplete", "filesystem_diff")
        for path in sorted(before.files.keys() | after.files.keys()):
            if path not in before.files:
                operation = "file.created" if before.complete else "file.discovered"
            elif path not in after.files:
                operation = "file.removed" if after.complete else "file.unobserved"
            elif before.files[path] != after.files[path]:
                operation = "file.changed"
            else:
                continue
            await self.record(run_id, path, operation, "filesystem_diff")

    async def projection(self) -> dict[str, Any]:
        return await self.database.read(
            lambda db: {
                "leases": [dict(row) for row in db.execute("SELECT * FROM path_leases")],
                "events": [
                    dict(row)
                    for row in db.execute(
                        "SELECT * FROM path_events ORDER BY rowid DESC LIMIT 250",
                    )
                ],
                "notice": (
                    "Declared roots and Core/provider evidence only; opaque agent reads are not "
                    "fully observed. Uncertain writers retain their roots until kernel-job "
                    "reconciliation proves stop."
                ),
            }
        )
