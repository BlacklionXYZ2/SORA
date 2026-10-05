"""Canonical, owner-scoped run pagination over existing records, not a history store."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Sequence

from sora.contracts.content import ContentReference
from sora.contracts.models import AgentRunRecord, NormalizedResult, TaskRecord
from sora.contracts.task_history import RunArtifact, RunHistoryItem, TaskRunEvidence, TaskRunPage

NOTE = (
    "Attempt records are canonical; completion/results are validated provider reports, not "
    "independent proof of every action. Paging excludes later admissions until Refresh; "
    "existing attempt statuses are live. File paths are inert unless Core registers them."
)


def run_page(
    db: sqlite3.Connection, owner: str, task_id: str, limit: int, cursor: str | None
) -> TaskRunPage:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    task = _task(db, owner, task_id)
    ceiling = int(
        db.execute(
            "SELECT COALESCE(MAX(rowid),0) FROM agent_runs WHERE task_id=?", (task_id,)
        ).fetchone()[0]
    )
    before = ceiling + 1
    if cursor is not None:
        try:
            if len(cursor) > 1024:
                raise ValueError("cursor too long")
            parts = json.loads(
                base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True)
            )
            if (
                not isinstance(parts, list)
                or len(parts) != 3
                or parts[0] != task_id
                or type(parts[1]) is not int
                or type(parts[2]) is not int
                or not 0 <= parts[1] <= ceiling
                or not 1 <= parts[2] <= parts[1]
            ):
                raise ValueError("cursor identity/bounds mismatch")
            ceiling, before = parts[1], parts[2]
        except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as error:
            raise ValueError("Invalid task-bound history cursor") from error
    rows = db.execute(
        "SELECT r.rowid, r.payload, (SELECT n.result_id FROM normalized_results n "
        "WHERE n.run_id=r.run_id AND n.task_id=r.task_id ORDER BY n.rowid DESC LIMIT 1) "
        ", r.run_id "
        "FROM agent_runs r "
        "WHERE r.task_id=? AND r.rowid<=? AND r.rowid<? ORDER BY r.rowid DESC LIMIT ?",
        (task_id, ceiling, before, limit + 1),
    ).fetchall()
    page = rows[:limit]
    items = []
    for row in page:
        run = AgentRunRecord.model_validate_json(row[1])
        if run.task_id != task_id or run.run_id != row[3]:
            raise ValueError("Stored task-run identity mismatch")
        items.append(RunHistoryItem(run=run, result_id=row[2]))
    next_cursor = (
        base64.urlsafe_b64encode(json.dumps([task_id, ceiling, page[-1][0]]).encode())
        .decode()
        .rstrip("=")
        if len(rows) > limit
        else None
    )
    return TaskRunPage(
        task_id=task_id,
        task_status=task.status,
        active_run_id=task.active_run_id,
        runs=tuple(items),
        next_cursor=next_cursor,
        total=int(
            db.execute(
                "SELECT COUNT(*) FROM agent_runs WHERE task_id=? AND rowid<=?", (task_id, ceiling)
            ).fetchone()[0]
        ),
        projection_revision=_revision(db),
        evidence_note=NOTE,
    )


def run_evidence(
    db: sqlite3.Connection,
    owner: str,
    task_id: str,
    run_id: str,
    references: Sequence[ContentReference],
) -> TaskRunEvidence:
    task = _task(db, owner, task_id)
    row = db.execute(
        "SELECT payload FROM agent_runs WHERE task_id=? AND run_id=?", (task_id, run_id)
    ).fetchone()
    if row is None:
        raise LookupError("Run not found")
    run = AgentRunRecord.model_validate_json(row[0])
    row = db.execute(
        "SELECT payload FROM normalized_results WHERE task_id=? AND run_id=? "
        "ORDER BY rowid DESC LIMIT 1",
        (task_id, run_id),
    ).fetchone()
    report = NormalizedResult.model_validate_json(row[0]) if row else None
    if (
        run.task_id != task_id
        or run.run_id != run_id
        or report is not None
        and (report.task_id != task_id or report.run_id != run_id)
    ):
        raise ValueError("Stored task-run identity mismatch")
    result: dict[str, object] | None = None
    artifacts: list[RunArtifact] = []
    omitted: dict[str, int] = {}
    truncated = False
    if report is not None:
        result = {
            "result_id": report.result_id,
            "task_id": report.task_id,
            "run_id": report.run_id,
            "outcome": report.outcome.value,
        }
        budget = 32768
        for name in ("summary", "conclusion", "changelog_path", "changelog_entry"):
            value = getattr(report, name)
            if value is not None:
                text = str(value)[:budget]
                truncated |= len(text) != len(value)
                result[name] = text
                budget -= len(text)
        for name in (
            "warnings",
            "uncertainties",
            "actions_taken",
            "files_read",
            "files_changed",
            "commands_run",
            "task_updates",
        ):
            values = getattr(report, name)
            selected: list[str] = []
            for value in values[:64]:
                if len(value) > budget:
                    break  # Never fabricate/truncate a path or command into a different target.
                selected.append(value)
                budget -= len(value)
            result[name] = selected
            if len(values) > len(selected):
                omitted[name] = len(values) - len(selected)
        if report.error is not None:
            result["error"] = {
                "code": report.error.code.value,
                "message": report.error.message[:4096],
            }
            truncated |= len(report.error.message) > 4096
        changed = result.get("files_changed")
        paths = (
            [("reported file", path) for path in changed if isinstance(path, str)]
            if isinstance(changed, list)
            else []
        )
        if report.changelog_path and result.get("changelog_path") == report.changelog_path:
            paths.append(("reported changelog", report.changelog_path))
        reference_budget = 64
        for kind, path in paths:
            refs = tuple(
                ref.reference_id
                for ref in references
                if str(ref.path) == path
                and ref.owner_id == owner
                and ref.project_id == task.project_id
            )[:reference_budget]
            reference_budget -= len(refs)
            artifacts.append(RunArtifact(kind=kind, path=path, reference_ids=refs))
    return TaskRunEvidence(
        task_id=task_id,
        run=run,
        result=result,
        omitted_items=omitted,
        text_truncated=truncated,
        artifacts=tuple(artifacts),
        projection_revision=_revision(db),
        evidence_note=NOTE,
    )


def _task(db: sqlite3.Connection, owner: str, task_id: str) -> TaskRecord:
    row = db.execute(
        "SELECT payload FROM tasks WHERE task_id=? AND owner_id=?", (task_id, owner)
    ).fetchone()
    if row is None:
        raise LookupError("Task not found")
    task = TaskRecord.model_validate_json(row[0])
    if task.task_id != task_id or task.owner_id != owner:
        raise ValueError("Stored task ownership mismatch")
    return task


def _revision(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0])
