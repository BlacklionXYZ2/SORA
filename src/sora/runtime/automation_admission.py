"""Canonical occurrence admission and reconciliation; never relaunch ambiguous work."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from sora.contracts.automation import (
    MANUAL_ADMISSION_SECONDS,
    AutomationDefinition,
    AutomationOccurrence,
)
from sora.contracts.models import (
    AgentRunRecord,
    NormalizedResult,
    ProviderOutcome,
    RunStatus,
    TaskRecord,
    TaskStatus,
)
from sora.runtime.automation_clock import missed_disposition
from sora.runtime.automation_store import (
    AutomationConflict,
    AutomationStorageError,
    AutomationStore,
)
from sora.runtime.repository import SubmissionReceipt


class AutomationAdmission:
    def __init__(self, store: AutomationStore):
        self.store = store

    def occurrence_in(self, db: sqlite3.Connection, identifier: str) -> AutomationOccurrence:
        row = db.execute(
            "SELECT o.* FROM automation_occurrences o JOIN automation_definitions d "
            "ON d.automation_id=o.automation_id WHERE o.occurrence_id=? AND d.owner_id=? "
            "AND (d.project_id IS NULL OR d.project_id=?)",
            (identifier, self.store.owner, self.store.project),
        ).fetchone()
        if row is None:
            raise LookupError("Scoped occurrence not found")
        return self.store._occurrence(row)

    def key_in(self, db: sqlite3.Connection, identifier: str) -> str:
        self.occurrence_in(db, identifier)
        return str(
            db.execute(
                "SELECT submission_key FROM automation_occurrences WHERE occurrence_id=?",
                (identifier,),
            ).fetchone()[0]
        )

    def definition_in(
        self, db: sqlite3.Connection, value: AutomationOccurrence
    ) -> AutomationDefinition:
        return self.store._decode(self.store._row(db, value.automation_id, deleted=True))[0]

    def guard_in(self, db: sqlite3.Connection, identifier: str, *, now: datetime) -> None:
        value = self.occurrence_in(db, identifier)
        if (
            value.origin == "manual"
            and (now - value.recorded_at).total_seconds() > MANUAL_ADMISSION_SECONDS
        ):
            raise AutomationConflict("AUTOMATION_MANUAL_REQUEST_EXPIRED")
        definition = self.definition_in(db, value)
        if (
            value.status != "reserved"
            or definition.entity_version != value.definition_version
            or definition.state == "deleted"
            or value.origin == "scheduled"
            and definition.state != "active"
            or definition.spec.behavior != value.behavior
        ):
            raise AutomationConflict("AUTOMATION_RESERVATION_RETIRED")
        if db.execute(
            "SELECT 1 FROM automation_occurrences WHERE automation_id=? "
            "AND occurrence_id<>? AND status IN ('reserved','admitted','unknown') LIMIT 1",
            (value.automation_id, identifier),
        ).fetchone():
            raise AutomationConflict("AUTOMATION_OVERLAP")
        # No blind duplicate submission. Reconciliation must inspect canonical evidence first.
        if db.execute(
            "SELECT 1 FROM submissions WHERE idempotency_key=?",
            (self.key_in(db, identifier),),
        ).fetchone():
            raise AutomationConflict("AUTOMATION_SUBMISSION_EXISTS")

    def save_in(self, db: sqlite3.Connection, value: AutomationOccurrence) -> None:
        # Validate model_copy updates too; cannot store an impossible status/link combination.
        value = AutomationOccurrence.model_validate(value.model_dump())
        db.execute(
            "UPDATE automation_occurrences SET status=?,task_id=?,run_id=?,payload=? "
            "WHERE occurrence_id=?",
            (
                value.status,
                value.task_id,
                value.run_id,
                value.model_dump_json(),
                value.occurrence_id,
            ),
        )
        revision = self.store.repository._next_revision(db)
        self.store.repository._append_event(
            db,
            self.store.owner,
            revision,
            "automation.occurrence." + value.status,
            value.task_id,
            value.run_id,
            {
                "automation_id": value.automation_id,
                "occurrence_id": value.occurrence_id,
                "definition_version": value.definition_version,
                "origin": value.origin,
                "status": value.status,
                "reason": value.reason,
            },
        )

    def commit_in(
        self, db: sqlite3.Connection, identifier: str, receipt: SubmissionReceipt
    ) -> None:
        value = self.occurrence_in(db, identifier)
        if not receipt.created or value.status != "reserved":
            raise AutomationConflict("AUTOMATION_SUBMISSION_EXISTS")
        # Task, original run, submission, revision and occurrence event commit together.
        self.save_in(
            db,
            value.model_copy(
                update={
                    "status": "admitted",
                    "task_id": receipt.task.task_id,
                    "run_id": receipt.run.run_id,
                    "reason": None,
                }
            ),
        )

    def _evidence_in(
        self, db: sqlite3.Connection, value: AutomationOccurrence
    ) -> tuple[TaskRecord, AgentRunRecord] | None:
        submission = db.execute(
            "SELECT task_id,message_id FROM submissions WHERE idempotency_key=?",
            (self.key_in(db, value.occurrence_id),),
        ).fetchone()
        if submission is None:
            if value.task_id is not None:
                raise AutomationStorageError("Missing canonical submission evidence")
            return None
        task_row = db.execute("SELECT * FROM tasks WHERE task_id=?", (submission[0],)).fetchone()
        runs = db.execute(
            "SELECT * FROM agent_runs WHERE task_id=? "
            "AND json_extract(payload,'$.attempt')=1 LIMIT 2",
            (submission[0],),
        ).fetchall()
        message = db.execute(
            "SELECT owner_id,project_id,content FROM messages WHERE message_id=?", (submission[1],)
        ).fetchone()
        try:
            if task_row is None or len(runs) != 1 or message is None:
                raise ValueError()
            task = TaskRecord.model_validate_json(task_row["payload"])
            run = AgentRunRecord.model_validate_json(runs[0]["payload"])
            if (
                task.task_id != task_row["task_id"]
                or task.status.value != task_row["status"]
                or task.owner_id != self.store.owner
                or task.project_id != self.store.project
                or task_row["owner_id"] != task.owner_id
                or task_row["project_id"] != task.project_id
                or task.creator_message_id != submission[1]
                or run.run_id != runs[0]["run_id"]
                or run.task_id != task.task_id
                or runs[0]["task_id"] != run.task_id
                or run.status.value != runs[0]["status"]
                or tuple(message) != (self.store.owner, self.store.project, value.behavior.intent)
                or value.task_id is not None
                and (value.task_id, value.run_id) != (task.task_id, run.run_id)
            ):
                raise ValueError()
            return task, run
        except (TypeError, ValueError):
            raise AutomationStorageError("Invalid canonical submission evidence") from None

    def reconcile_in(
        self, db: sqlite3.Connection, identifier: str, *, now: datetime, started_at: datetime
    ) -> AutomationOccurrence:
        value = self.occurrence_in(db, identifier)
        if value.status not in {"reserved", "admitted", "unknown"}:
            return value
        evidence = self._evidence_in(db, value)
        updates: dict[str, object] = {}
        if evidence is not None:
            task, run = evidence
            updates = {
                "task_id": task.task_id,
                "run_id": run.run_id,
                "status": "admitted",
                "reason": None,
            }
            if (
                task.active_run_id != run.run_id
                or run.status in {RunStatus.INTERRUPTED, RunStatus.UNCERTAIN}
                or run.outcome == ProviderOutcome.UNKNOWN
                or task.status == TaskStatus.INTERRUPTED
            ):
                updates.update(status="unknown", reason="canonical_run_uncertain_or_replaced")
            elif run.status in {RunStatus.FAILED, RunStatus.CANCELLED}:
                updates.update(status="failed", reason="canonical_run_" + run.status.value)
            elif run.status == RunStatus.COMPLETED:
                result_row = db.execute(
                    "SELECT payload FROM normalized_results WHERE result_id=? "
                    "AND task_id=? AND run_id=?",
                    (task.result_ref, task.task_id, run.run_id),
                ).fetchone()
                try:
                    result = (
                        NormalizedResult.model_validate_json(result_row[0])
                        if result_row is not None
                        else None
                    )
                except ValueError:
                    raise AutomationStorageError("Invalid canonical result evidence") from None
                if (
                    task.status == TaskStatus.COMPLETED
                    and run.outcome == ProviderOutcome.COMPLETED
                    and result is not None
                    and result.task_id == task.task_id
                    and result.run_id == run.run_id
                    and result.result_id == task.result_ref
                    and result.outcome == ProviderOutcome.COMPLETED
                ):
                    updates.update(status="completed", reason=None)
                else:
                    updates.update(status="unknown", reason="completion_evidence_missing")
        elif value.status != "reserved":
            updates.update(status="unknown", reason="submission_evidence_missing")
        else:
            definition = self.definition_in(db, value)
            if (
                definition.entity_version != value.definition_version
                or definition.state == "deleted"
                or value.origin == "scheduled"
                and definition.state != "active"
            ):
                updates.update(status="blocked", reason="definition_changed_before_admission")
            elif value.origin == "scheduled":
                disposition = missed_disposition(
                    definition.spec,
                    value.slot,
                    now,
                    recovered=value.recorded_at.astimezone(UTC) < started_at,
                    overlapping=False,
                )
                if disposition not in {"admit", "wait"}:
                    updates.update(status="skipped", reason=disposition)
            elif (now - value.recorded_at).total_seconds() > MANUAL_ADMISSION_SECONDS:
                updates.update(status="blocked", reason="manual_request_expired")
        updated = value.model_copy(update=updates)
        if updated != value:
            self.save_in(db, updated)
        return updated

    async def reconcile(
        self, identifier: str, *, now: datetime, started_at: datetime
    ) -> AutomationOccurrence:
        return await self.store.repository.database.write(
            lambda db: self.reconcile_in(db, identifier, now=now, started_at=started_at)
        )

    async def block(self, identifier: str, reason: str) -> None:
        def write(db: sqlite3.Connection) -> None:
            value = self.occurrence_in(db, identifier)
            # An exception after task commit must never turn real admission into a retry.
            if value.status == "reserved" and self._evidence_in(db, value) is None:
                self.save_in(db, value.model_copy(update={"status": "blocked", "reason": reason}))

        await self.store.repository.database.write(write)
