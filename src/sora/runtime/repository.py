"""Atomic scheduling, lease, status, trace, and outbox persistence."""

# ruff: noqa: E501 -- SQL statements stay whole for direct schema comparison.

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Callable
from datetime import datetime

from pydantic import Field

from sora.contracts.base import StrictModel
from sora.contracts.content import ReferenceCandidate
from sora.contracts.editor import EditorContextSnapshot
from sora.contracts.models import (
    AgentRunRecord,
    AgentSessionRecord,
    NormalizedResult,
    ProviderOutcome,
    ReasoningEffort,
    RunStatus,
    SessionStatus,
    TaskRecord,
    TaskStatus,
    WorkspaceMode,
)
from sora.contracts.transitions import validate_run_transition, validate_task_transition
from sora.persistence.records import MessageRecord
from sora.persistence.repository import SoraRepository
from sora.security.redaction import redact_value


class SubmissionReceipt(StrictModel):
    task: TaskRecord
    run: AgentRunRecord
    message_id: str
    acknowledgement_id: str
    acknowledgement: str
    created: bool


class PlannedTaskReceipt(StrictModel):
    task: TaskRecord
    created: bool


class TraceRecord(StrictModel):
    trace_id: str
    correlation_id: str
    message_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    phase: str
    timestamp: datetime
    duration_ms: float | None = Field(default=None, ge=0)
    fields: dict[str, object] = Field(default_factory=dict)


class OutboxRecord(StrictModel):
    event_id: str
    payload: str


class RuntimeRepository:
    def __init__(self, repository: SoraRepository):
        self.repository = repository
        self.database = repository.database

    async def update_board_card(
        self, task_id: str, *, owner_id: str, project_id: str,
        action: str, actor: str, column: str | None = None,
        assigned_agent: str | None = None, expected_version: int | None = None,
        now: datetime,
    ) -> int:
        """Change only the board overlay; task/run evidence remains untouched."""
        if action not in {"assign", "move", "remove"}:
            raise ValueError("invalid board action")
        if action == "move" and column not in {"TODO", "DOING", "DONE"}:
            raise ValueError("invalid board column")
        if action == "assign" and assigned_agent not in {
            "codex", "claude", "hermes", "antigravity", "sora", "unassigned"
        }:
            raise ValueError("invalid assigned agent")

        def write(db: sqlite3.Connection) -> int:
            task = db.execute(
                "SELECT owner_id, project_id FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
            if task is None or task["owner_id"] != owner_id or task["project_id"] != project_id:
                raise LookupError("board card is outside the active scope")
            previous = db.execute(
                "SELECT column_name, assigned_agent, archived_at, version FROM board_cards WHERE task_id=?",
                (task_id,),
            ).fetchone()
            current_version = int(previous["version"]) if previous is not None else 0
            if expected_version is not None and expected_version != current_version:
                raise ValueError("board card changed before this edit")
            if previous is not None and previous["archived_at"] is not None:
                raise ValueError("board card has been removed")
            next_column = column if action == "move" else (
                previous["column_name"] if previous is not None else None
            )
            next_agent = assigned_agent if action == "assign" else (
                previous["assigned_agent"] if previous is not None else None
            )
            archived_at = now.isoformat() if action == "remove" else None
            version = current_version + 1
            db.execute(
                "INSERT INTO board_cards(task_id, column_name, assigned_agent, archived_at, version, updated_by, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(task_id) DO UPDATE SET "
                "column_name=excluded.column_name, assigned_agent=excluded.assigned_agent, "
                "archived_at=excluded.archived_at, version=excluded.version, "
                "updated_by=excluded.updated_by, updated_at=excluded.updated_at",
                (task_id, next_column, next_agent, archived_at, version, actor, now.isoformat()),
            )
            db.execute(
                "INSERT INTO board_card_events(event_id, task_id, action, actor, column_name, assigned_agent, occurred_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"board-event-{uuid.uuid4()}", task_id, action, actor,
                 next_column, next_agent, now.isoformat()),
            )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, f"board.card.{action}", task_id, None)
            return version

        return await self.database.write(write)

    async def plan_task(
        self, *, owner_id: str, project_id: str, conversation_id: str,
        intent: str, idempotency_key: str, now: datetime,
    ) -> PlannedTaskReceipt:
        """Persist one canonical TODO without creating or queueing an agent run."""

        def write(db: sqlite3.Connection) -> PlannedTaskReceipt:
            existing = db.execute(
                "SELECT task_id, intent FROM board_plan_requests WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                if existing["intent"] != intent:
                    raise ValueError("plan idempotency key was reused with a different intent")
                task = self._task(db, existing["task_id"])
                if task.owner_id != owner_id or task.project_id != project_id:
                    raise ValueError("plan idempotency key belongs to a different scope")
                return PlannedTaskReceipt(task=task, created=False)
            task_id = f"task-{uuid.uuid4()}"
            message_id = f"message-{uuid.uuid4()}"
            acknowledgement_id = f"message-{uuid.uuid4()}"
            task = TaskRecord(
                task_id=task_id, owner_id=owner_id, project_id=project_id,
                creator_message_id=message_id, status=TaskStatus.PLANNED,
                requested_backend="auto", base_revision=self._revision(db),
                constraints=(intent,), created_at=now, updated_at=now,
            )
            for record in (
                MessageRecord(
                    message_id=message_id, conversation_id=conversation_id,
                    owner_id=owner_id, project_id=project_id, role="user",
                    content=f"Fix this later: {intent}", provenance="owner board plan",
                    created_at=now,
                ),
                MessageRecord(
                    message_id=acknowledgement_id, conversation_id=conversation_id,
                    owner_id=owner_id, project_id=project_id, role="assistant",
                    content="Saved to TODO. No specialist has been started.",
                    provenance="deterministic board acknowledgement", created_at=now,
                ),
            ):
                db.execute(
                    "INSERT INTO messages(message_id, conversation_id, owner_id, project_id, role, content, provenance, sensitivity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record.message_id, record.conversation_id, record.owner_id,
                     record.project_id, record.role, record.content, record.provenance,
                     record.sensitivity, record.created_at.isoformat()),
                )
            db.execute(
                "INSERT INTO tasks(task_id, owner_id, project_id, status, entity_version, payload) VALUES (?, ?, ?, ?, 1, ?)",
                (task_id, owner_id, project_id, task.status.value, task.model_dump_json()),
            )
            db.execute(
                "INSERT INTO board_plan_requests(idempotency_key, task_id, intent, created_at) VALUES (?, ?, ?, ?)",
                (idempotency_key, task_id, intent, now.isoformat()),
            )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "message.finalized", task_id, None)
            self._append_event(db, owner_id, revision, "task.planned", task_id, None)
            return PlannedTaskReceipt(task=task, created=True)

        return await self.database.write(write)

    async def start_planned_task(
        self, task_id: str, *, owner_id: str, project_id: str,
        provider: str, requested_backend: str, now: datetime,
        max_active_tasks: int,
        local_delegation_epoch: int | None = None,
        requested_model: str | None = None,
        requested_effort: ReasoningEffort | None = None,
        working_directory: str | None = None,
        workspace_mode: WorkspaceMode | None = None,
        workspace_base_ref: str | None = None,
    ) -> AgentRunRecord:
        """Atomically attach the first run to an existing planned task."""

        def write(db: sqlite3.Connection) -> AgentRunRecord:
            task = self._task(db, task_id)
            if task.owner_id != owner_id or task.project_id != project_id:
                raise LookupError("planned task is outside the active scope")
            if task.status is not TaskStatus.PLANNED:
                raise ValueError("only a planned task can be started from the board")
            active_count = int(db.execute(
                "SELECT COUNT(*) FROM tasks WHERE owner_id=? AND status NOT IN (?, ?, ?, ?)",
                (owner_id, TaskStatus.PLANNED.value, TaskStatus.COMPLETED.value,
                 TaskStatus.FAILED.value, TaskStatus.CANCELLED.value),
            ).fetchone()[0])
            if active_count >= max_active_tasks:
                raise RuntimeError("runtime task capacity is currently exhausted")
            validate_task_transition(task.status, TaskStatus.QUEUED)
            run = AgentRunRecord(
                run_id=f"run-{uuid.uuid4()}", task_id=task_id, attempt=1,
                provider=provider, status=RunStatus.PENDING,
                local_delegation_epoch=local_delegation_epoch,
            )
            updated = TaskRecord.model_validate({
                **task.model_dump(), "status": TaskStatus.QUEUED,
                "requested_backend": requested_backend,
                "requested_model": requested_model, "requested_effort": requested_effort,
                "working_directory": working_directory, "workspace_mode": workspace_mode,
                "workspace_base_ref": workspace_base_ref,
                "effective_backend": provider, "active_run_id": run.run_id,
                "updated_at": now,
            })
            db.execute(
                "INSERT INTO agent_runs(run_id, task_id, status, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, task_id, run.status.value, run.model_dump_json()),
            )
            db.execute(
                "UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                (updated.status.value, updated.model_dump_json(), task_id),
            )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "task.started", task_id, run.run_id)
            self._append_event(db, owner_id, revision, "run.created", task_id, run.run_id)
            return run

        return await self.database.write(write)

    async def submit(
        self,
        *,
        owner_id: str,
        project_id: str,
        conversation_id: str,
        intent: str,
        idempotency_key: str,
        now: datetime,
        provider: str,
        requested_backend: str | None = None,
        requested_model: str | None = None,
        requested_effort: ReasoningEffort | None = None,
        working_directory: str | None = None,
        workspace_mode: WorkspaceMode | None = None,
        workspace_base_ref: str | None = None,
        editor_context: EditorContextSnapshot | None = None,
        reference_context: tuple[ReferenceCandidate, ...] = (),
        max_active_tasks: int | None = None,
        local_delegation_epoch: int | None = None,
        companion_brief: str | None = None,
        admission_check: Callable[[], None] | None = None,
        admission_guard: Callable[[sqlite3.Connection], None] | None = None,
        admission_commit: Callable[[sqlite3.Connection, SubmissionReceipt], None] | None = None,
    ) -> SubmissionReceipt:
        def write(db: sqlite3.Connection) -> SubmissionReceipt:
            if admission_check is not None:
                admission_check()
            if admission_guard is not None:
                admission_guard(db)
            duplicate = db.execute(
                "SELECT task_id, message_id, acknowledgement_id FROM submissions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if duplicate:
                task = self._task(db, duplicate["task_id"])
                if (task.requested_model != requested_model
                        or task.requested_effort != requested_effort
                        or task.working_directory != working_directory
                        or task.workspace_mode != workspace_mode
                        or task.workspace_base_ref != workspace_base_ref
                        or task.requested_backend != (requested_backend or provider)):
                    raise ValueError("idempotency key was reused with a different agent/model selection")
                if task.companion_brief != companion_brief:
                    raise ValueError("idempotency key was reused with a different companion brief")
                existing_editor = (
                    task.editor_context.model_dump(exclude={"context_id", "verified_at"})
                    if task.editor_context is not None
                    else None
                )
                submitted_editor = (
                    editor_context.model_dump(exclude={"context_id", "verified_at"})
                    if editor_context is not None
                    else None
                )
                if existing_editor != submitted_editor:
                    raise ValueError("idempotency key was reused with different editor context")
                if task.reference_context != reference_context:
                    raise ValueError("idempotency key was reused with different reference context")
                run = self._run(db, task.active_run_id or "")
                acknowledgement = (
                    db.execute(
                        "SELECT message_id, content FROM messages WHERE message_id=?",
                        (duplicate["acknowledgement_id"],),
                    ).fetchone()
                    if duplicate["acknowledgement_id"]
                    else None
                )
                if acknowledgement is None:
                    acknowledgement = db.execute(
                        "SELECT message_id, content FROM messages WHERE conversation_id=? AND role='assistant' AND created_at=(SELECT created_at FROM messages WHERE message_id=?) ORDER BY message_id LIMIT 1",
                        (conversation_id, duplicate["message_id"]),
                    ).fetchone()
                if acknowledgement is None:
                    raise RuntimeError("submission acknowledgement is missing")
                receipt = SubmissionReceipt(
                    task=task,
                    run=run,
                    message_id=duplicate["message_id"],
                    acknowledgement_id=acknowledgement["message_id"],
                    acknowledgement=acknowledgement["content"],
                    created=False,
                )
                if admission_commit is not None:
                    admission_commit(db, receipt)
                return receipt

            if max_active_tasks is not None:
                active_count = int(
                    db.execute(
                        "SELECT COUNT(*) FROM tasks WHERE status NOT IN (?, ?, ?, ?)",
                        (
                            TaskStatus.PLANNED.value,
                            TaskStatus.COMPLETED.value,
                            TaskStatus.FAILED.value,
                            TaskStatus.CANCELLED.value,
                        ),
                    ).fetchone()[0]
                )
                if active_count >= max_active_tasks:
                    raise RuntimeError(
                        f"runtime task capacity {max_active_tasks} is currently exhausted"
                    )

            task_id = f"task-{uuid.uuid4()}"
            run_id = f"run-{uuid.uuid4()}"
            message_id = f"message-{uuid.uuid4()}"
            acknowledgement_id = f"message-{uuid.uuid4()}"
            acknowledgement_text = (
                "I started a queued reasoning task. Its completion will be reported only "
                "after a validated result is stored."
            )
            if companion_brief is not None:
                acknowledgement_text = (
                    f"I queued specialist task {task_id} with {provider}. "
                    f"Model: {requested_model or 'saved/configured default'}. "
                    f"Project: {working_directory or 'no project selected'}; "
                    f"mode: {workspace_mode or 'configured specialist'}. "
                    "Queued is not completed. Check Activity for progress and the final evidence."
                )
            task = TaskRecord(
                task_id=task_id,
                owner_id=owner_id,
                project_id=project_id,
                creator_message_id=message_id,
                status=TaskStatus.QUEUED,
                requested_backend=requested_backend or provider,
                requested_model=requested_model,
                requested_effort=requested_effort,
                working_directory=working_directory,
                workspace_mode=workspace_mode,
                workspace_base_ref=workspace_base_ref,
                companion_brief=companion_brief,
                effective_backend=provider,
                base_revision=self._revision(db),
                active_run_id=run_id,
                editor_context=editor_context,
                reference_context=reference_context,
                created_at=now,
                updated_at=now,
            )
            run = AgentRunRecord(
                run_id=run_id,
                task_id=task_id,
                attempt=1,
                provider=provider,
                status=RunStatus.PENDING,
                local_delegation_epoch=local_delegation_epoch,
            )
            messages = (
                MessageRecord(
                    message_id=message_id,
                    conversation_id=conversation_id,
                    owner_id=owner_id,
                    project_id=project_id,
                    role="user",
                    content=intent,
                    provenance="user input",
                    created_at=now,
                ),
                MessageRecord(
                    message_id=acknowledgement_id,
                    conversation_id=conversation_id,
                    owner_id=owner_id,
                    project_id=project_id,
                    role="assistant",
                    content=acknowledgement_text,
                    provenance="deterministic runtime",
                    created_at=now,
                ),
            )
            for message in messages:
                db.execute(
                    "INSERT INTO messages(message_id, conversation_id, owner_id, project_id, role, content, provenance, sensitivity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        message.message_id,
                        message.conversation_id,
                        message.owner_id,
                        message.project_id,
                        message.role,
                        message.content,
                        message.provenance,
                        message.sensitivity,
                        message.created_at.isoformat(),
                    ),
                )
            db.execute(
                "INSERT INTO tasks(task_id, owner_id, project_id, status, entity_version, payload) VALUES (?, ?, ?, ?, 1, ?)",
                (task_id, owner_id, project_id, task.status.value, task.model_dump_json()),
            )
            db.execute(
                "INSERT INTO agent_runs(run_id, task_id, status, payload) VALUES (?, ?, ?, ?)",
                (run_id, task_id, run.status.value, run.model_dump_json()),
            )
            db.execute(
                "INSERT INTO submissions(idempotency_key, task_id, message_id, created_at, acknowledgement_id) VALUES (?, ?, ?, ?, ?)",
                (idempotency_key, task_id, message_id, now.isoformat(), acknowledgement_id),
            )
            revision = self._next_revision(db)
            for event_type in ("message.finalized", "task.created", "run.created"):
                self._append_event(db, owner_id, revision, event_type, task_id, run_id)
            receipt = SubmissionReceipt(
                task=task,
                run=run,
                message_id=message_id,
                acknowledgement_id=acknowledgement_id,
                acknowledgement=acknowledgement_text,
                created=True,
            )
            if admission_commit is not None:
                admission_commit(db, receipt)
            return receipt

        return await self.database.write(write)

    async def pending_run_ids(self) -> list[str]:
        return await self.database.read(
            lambda db: [
                str(row[0])
                for row in db.execute(
                    "SELECT run_id FROM agent_runs WHERE status=? ORDER BY rowid",
                    (RunStatus.PENDING.value,),
                )
            ]
        )

    async def active_run_ids(self) -> list[str]:
        return await self.database.read(
            lambda db: [
                str(row[0])
                for row in db.execute(
                    "SELECT run_id FROM agent_runs WHERE status IN (?, ?, ?) ORDER BY rowid",
                    (
                        RunStatus.PENDING.value,
                        RunStatus.LAUNCHING.value,
                        RunStatus.RUNNING.value,
                    ),
                )
            ]
        )

    async def acquire_lease(
        self,
        run_id: str,
        *,
        lease_owner: str,
        now: datetime,
        expires_at: datetime,
        deadline: datetime,
    ) -> bool:
        def write(db: sqlite3.Connection) -> bool:
            run = self._run(db, run_id)
            if run.status is not RunStatus.PENDING:
                return False
            task = self._task(db, run.task_id)
            validate_run_transition(run.status, RunStatus.LAUNCHING)
            validate_task_transition(task.status, TaskStatus.ROUTING)
            updated_run = run.model_copy(
                update={
                    "status": RunStatus.LAUNCHING,
                    "lease_expires_at": expires_at,
                }
            )
            updated_task = task.model_copy(update={"status": TaskStatus.ROUTING, "updated_at": now})
            db.execute(
                "UPDATE agent_runs SET status=?, payload=? WHERE run_id=?",
                (updated_run.status.value, updated_run.model_dump_json(), run_id),
            )
            db.execute(
                "UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                (updated_task.status.value, updated_task.model_dump_json(), task.task_id),
            )
            db.execute(
                "INSERT INTO runtime_leases(run_id, lease_owner, acquired_at, heartbeat_at, expires_at, deadline) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run_id,
                    lease_owner,
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                    deadline.isoformat(),
                ),
            )
            revision = self._next_revision(db)
            self._append_event(db, task.owner_id, revision, "run.launching", task.task_id, run_id)
            return True

        return await self.database.write(write)

    async def mark_running(self, run_id: str, now: datetime) -> None:
        await self._transition(
            run_id,
            run_status=RunStatus.RUNNING,
            task_status=TaskStatus.REASONING,
            now=now,
            event_type="run.running",
        )

    async def finish(
        self,
        run_id: str,
        *,
        run_status: RunStatus,
        task_status: TaskStatus,
        outcome: ProviderOutcome,
        result_ref: str | None,
        now: datetime,
    ) -> None:
        await self._transition(
            run_id,
            run_status=run_status,
            task_status=task_status,
            now=now,
            event_type=f"run.{run_status.value}",
            outcome=outcome,
            result_ref=result_ref,
        )

    async def request_cancel(self, run_id: str, now: datetime) -> bool:
        def write(db: sqlite3.Connection) -> bool:
            row = db.execute("SELECT payload FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
            if row is None:
                return False
            run = AgentRunRecord.model_validate_json(row[0])
            if run.status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED,
                              RunStatus.CANCEL_REQUESTED}:
                return False
            task = self._task(db, run.task_id)
            pending = run.status is RunStatus.PENDING
            run_status = RunStatus.CANCELLED if pending else RunStatus.CANCEL_REQUESTED
            task_status = TaskStatus.CANCELLED if pending else TaskStatus.CANCEL_REQUESTED
            validate_run_transition(run.status, run_status)
            validate_task_transition(task.status, task_status)
            update: dict[str, object] = {"status": run_status}
            if pending:
                update.update(finished_at=now, outcome=ProviderOutcome.CANCELLED)
            updated_run = AgentRunRecord.model_validate({**run.model_dump(), **update})
            updated_task = TaskRecord.model_validate({
                **task.model_dump(), "status": task_status, "updated_at": now,
            })
            db.execute("UPDATE agent_runs SET status=?, payload=? WHERE run_id=?",
                       (run_status.value, updated_run.model_dump_json(), run_id))
            db.execute("UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                       (task_status.value, updated_task.model_dump_json(), task.task_id))
            revision = self._next_revision(db)
            self._append_event(db, task.owner_id, revision, f"run.{run_status.value}",
                               task.task_id, run_id)
            return True

        # Admission and cancellation race on the same atomic row transition, not a prior read.
        return await self.database.write(write)

    async def _transition(
        self,
        run_id: str,
        *,
        run_status: RunStatus,
        task_status: TaskStatus,
        now: datetime,
        event_type: str,
        outcome: ProviderOutcome | None = None,
        result_ref: str | None = None,
    ) -> None:
        def write(db: sqlite3.Connection) -> None:
            run = self._run(db, run_id)
            task = self._task(db, run.task_id)
            if run.status is RunStatus.CANCEL_REQUESTED and run_status is RunStatus.RUNNING:
                return  # A late launch acknowledgement cannot undo cancellation.
            validate_run_transition(run.status, run_status)
            validate_task_transition(task.status, task_status)
            run_update: dict[str, object] = {"status": run_status}
            if run_status is RunStatus.RUNNING and run.started_at is None:
                run_update["started_at"] = now
            if run_status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                run_update.update({"finished_at": now, "outcome": outcome})
            updated_run = AgentRunRecord.model_validate({**run.model_dump(), **run_update})
            task_update: dict[str, object] = {"status": task_status, "updated_at": now}
            if result_ref is not None:
                task_update["result_ref"] = result_ref
            updated_task = TaskRecord.model_validate({**task.model_dump(), **task_update})
            db.execute(
                "UPDATE agent_runs SET status=?, payload=? WHERE run_id=?",
                (run_status.value, updated_run.model_dump_json(), run_id),
            )
            db.execute(
                "UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                (task_status.value, updated_task.model_dump_json(), task.task_id),
            )
            revision = self._next_revision(db)
            self._append_event(db, task.owner_id, revision, event_type, task.task_id, run_id)

        await self.database.write(write)

    async def get_run(self, run_id: str) -> AgentRunRecord | None:
        def read(db: sqlite3.Connection) -> AgentRunRecord | None:
            row = db.execute("SELECT payload FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
            return AgentRunRecord.model_validate_json(row[0]) if row else None

        return await self.database.read(read)

    async def latest_active_session(
        self, *, provider: str, project_id: str | None
    ) -> AgentSessionRecord | None:
        """The most recently used resumable session for a provider in a project, if any.

        A session is only offered back when it is still active, marked resume-capable, and belongs
        to this project - project A's thread is never handed to project B.
        """

        def read(db: sqlite3.Connection) -> AgentSessionRecord | None:
            rows = db.execute(
                "SELECT payload FROM agent_sessions WHERE provider=? AND status=?",
                (provider, SessionStatus.ACTIVE.value),
            ).fetchall()
            candidates: list[AgentSessionRecord] = []
            for row in rows:
                try:
                    session = AgentSessionRecord.model_validate_json(row["payload"])
                except ValueError:
                    continue
                if session.project_id == project_id and session.resume_supported:
                    candidates.append(session)
            if not candidates:
                return None
            return max(candidates, key=lambda item: item.last_seen_at)

        return await self.database.read(read)

    async def attach_native_session(
        self,
        run_id: str,
        *,
        native_session_id: str,
        context_fingerprint: str,
        now: datetime,
    ) -> AgentSessionRecord:
        """Atomically map a run to a durable provider-native session."""

        def write(db: sqlite3.Connection) -> AgentSessionRecord:
            run = self._run(db, run_id)
            task = self._task(db, run.task_id)
            existing = db.execute(
                "SELECT payload FROM agent_sessions WHERE provider=? AND native_session_id=?",
                (run.provider, native_session_id),
            ).fetchone()
            if existing is None:
                session = AgentSessionRecord(
                    session_id=f"session-{uuid.uuid4()}",
                    task_id=task.task_id,
                    owner_id=task.owner_id,
                    project_id=task.project_id,
                    provider=run.provider,
                    native_session_id=native_session_id,
                    status=SessionStatus.ACTIVE,
                    resume_supported=True,
                    context_fingerprint=context_fingerprint,
                    created_at=now,
                    last_seen_at=now,
                )
                db.execute(
                    "INSERT INTO agent_sessions(session_id, task_id, provider, native_session_id, status, payload) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        session.session_id,
                        session.task_id,
                        session.provider,
                        session.native_session_id,
                        session.status.value,
                        session.model_dump_json(),
                    ),
                )
            else:
                previous = AgentSessionRecord.model_validate_json(existing["payload"])
                session = previous.model_copy(update={"last_seen_at": now})
                db.execute(
                    "UPDATE agent_sessions SET status=?, payload=? WHERE session_id=?",
                    (session.status.value, session.model_dump_json(), session.session_id),
                )
            updated_run = run.model_copy(update={"native_session_id": native_session_id})
            db.execute(
                "UPDATE agent_runs SET payload=? WHERE run_id=?",
                (updated_run.model_dump_json(), run_id),
            )
            revision = self._next_revision(db)
            self._append_event(
                db,
                task.owner_id,
                revision,
                "session.attached",
                task.task_id,
                run_id,
            )
            return session

        return await self.database.write(write)

    async def set_effective_provider(self, run_id: str, provider: str) -> None:
        """Persist the actual bounded-fallback provider before launching it."""

        def write(db: sqlite3.Connection) -> None:
            run = self._run(db, run_id)
            task = self._task(db, run.task_id)
            updated_run = run.model_copy(update={"provider": provider})
            updated_task = task.model_copy(update={"effective_backend": provider})
            db.execute(
                "UPDATE agent_runs SET payload=? WHERE run_id=?",
                (updated_run.model_dump_json(), run_id),
            )
            db.execute(
                "UPDATE tasks SET entity_version=entity_version+1, payload=? WHERE task_id=?",
                (updated_task.model_dump_json(), task.task_id),
            )
            revision = self._next_revision(db)
            self._append_event(
                db,
                task.owner_id,
                revision,
                "routing.provider_changed",
                task.task_id,
                run_id,
            )

        await self.database.write(write)

    async def get_task(self, task_id: str) -> TaskRecord | None:
        return await self.repository.get_task(task_id)

    async def retry_task(
        self,
        task_id: str,
        *,
        now: datetime,
        max_attempts: int,
        local_delegation_epoch: int | None = None,
    ) -> AgentRunRecord:
        """Create one new pending attempt without mutating prior run evidence."""

        def write(db: sqlite3.Connection) -> AgentRunRecord:
            task = self._task(db, task_id)
            if task.status not in {
                TaskStatus.COMPLETED,
                TaskStatus.FAILED,
                TaskStatus.CANCELLED,
                TaskStatus.INTERRUPTED,
            }:
                raise ValueError(f"task {task_id} is not retryable while {task.status.value}")
            previous = self._run(db, task.active_run_id or "")
            attempt = previous.attempt + 1
            if attempt > max_attempts:
                raise ValueError(f"task {task_id} reached its {max_attempts}-attempt limit")
            validate_task_transition(task.status, TaskStatus.QUEUED)
            run = AgentRunRecord(
                run_id=f"run-{uuid.uuid4()}",
                task_id=task_id,
                attempt=attempt,
                provider=previous.provider,
                status=RunStatus.PENDING,
                local_delegation_epoch=local_delegation_epoch,
            )
            updated_task = TaskRecord.model_validate(
                {
                    **task.model_dump(),
                    "status": TaskStatus.QUEUED,
                    "active_run_id": run.run_id,
                    "result_ref": None,
                    "updated_at": now,
                }
            )
            db.execute(
                "INSERT INTO agent_runs(run_id, task_id, status, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, task_id, run.status.value, run.model_dump_json()),
            )
            db.execute(
                "UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                (updated_task.status.value, updated_task.model_dump_json(), task_id),
            )
            revision = self._next_revision(db)
            self._append_event(db, task.owner_id, revision, "task.retried", task_id, run.run_id)
            return run

        return await self.database.write(write)

    async def create_branch_run(
        self,
        *,
        task_id: str,
        run_id: str,
        provider: str,
        now: datetime,
        local_delegation_epoch: int | None = None,
    ) -> AgentRunRecord:
        def write(db: sqlite3.Connection) -> AgentRunRecord:
            self._task(db, task_id)
            run = AgentRunRecord(
                run_id=run_id,
                task_id=task_id,
                attempt=1,
                provider=provider,
                status=RunStatus.PENDING,
                local_delegation_epoch=local_delegation_epoch,
            )
            db.execute(
                "INSERT INTO agent_runs(run_id, task_id, status, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, task_id, run.status.value, run.model_dump_json()),
            )
            return run

        return await self.database.write(write)

    async def transition_branch_run(
        self,
        run_id: str,
        *,
        status: RunStatus,
        now: datetime,
        outcome: ProviderOutcome | None = None,
    ) -> AgentRunRecord:
        """Advance a fan-out branch without mutating the coordinator task lifecycle."""

        def write(db: sqlite3.Connection) -> AgentRunRecord:
            run = self._run(db, run_id)
            if run.status is RunStatus.CANCEL_REQUESTED and status in {
                RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED,
            }:
                return run
            validate_run_transition(run.status, status)
            update: dict[str, object] = {"status": status}
            if status is RunStatus.RUNNING and run.started_at is None:
                update["started_at"] = now
            if status in {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}:
                if outcome is None:
                    raise ValueError("terminal branch status requires an outcome")
                update.update({"finished_at": now, "outcome": outcome})
            elif outcome is not None:
                raise ValueError("non-terminal branch status cannot carry an outcome")
            updated = AgentRunRecord.model_validate({**run.model_dump(), **update})
            db.execute(
                "UPDATE agent_runs SET status=?, payload=? WHERE run_id=?",
                (updated.status.value, updated.model_dump_json(), run_id),
            )
            task = self._task(db, run.task_id)
            revision = self._next_revision(db)
            self._append_event(
                db,
                task.owner_id,
                revision,
                f"fanout.branch.{status.value}",
                task.task_id,
                run_id,
            )
            return updated

        return await self.database.write(write)

    async def result_for_task(self, task_id: str) -> NormalizedResult | None:
        def read(db: sqlite3.Connection) -> NormalizedResult | None:
            row = db.execute(
                "SELECT payload FROM normalized_results WHERE task_id=? ORDER BY rowid DESC LIMIT 1",
                (task_id,),
            ).fetchone()
            return NormalizedResult.model_validate_json(row[0]) if row else None

        return await self.database.read(read)

    async def list_tasks(self) -> list[TaskRecord]:
        return await self.database.read(
            lambda db: [
                TaskRecord.model_validate_json(row[0])
                for row in db.execute("SELECT payload FROM tasks ORDER BY rowid")
            ]
        )

    async def list_runs(self, task_id: str) -> list[AgentRunRecord]:
        return await self.database.read(
            lambda db: [
                AgentRunRecord.model_validate_json(row[0])
                for row in db.execute(
                    "SELECT payload FROM agent_runs WHERE task_id=? ORDER BY rowid", (task_id,)
                )
            ]
        )

    async def release_lease(self, run_id: str) -> None:
        await self.database.write(
            lambda db: db.execute("DELETE FROM runtime_leases WHERE run_id=?", (run_id,))
        )

    async def reconcile_expired(
        self, now: datetime, *, include_unexpired: bool = False
    ) -> list[str]:
        def write(db: sqlite3.Connection) -> list[str]:
            rows = (
                db.execute("SELECT run_id FROM runtime_leases ORDER BY run_id").fetchall()
                if include_unexpired
                else db.execute(
                    "SELECT run_id FROM runtime_leases WHERE expires_at<=? ORDER BY run_id",
                    (now.isoformat(),),
                ).fetchall()
            )
            reconciled: list[str] = []
            for row in rows:
                run = self._run(db, row["run_id"])
                task = self._task(db, run.task_id)
                if run.status in {
                    RunStatus.LAUNCHING,
                    RunStatus.RUNNING,
                    RunStatus.CANCEL_REQUESTED,
                    RunStatus.UNCERTAIN,
                }:
                    updated_run = run.model_copy(update={"status": RunStatus.INTERRUPTED})
                    updated_task = task.model_copy(
                        update={"status": TaskStatus.INTERRUPTED, "updated_at": now}
                    )
                    db.execute(
                        "UPDATE agent_runs SET status=?, payload=? WHERE run_id=?",
                        (
                            RunStatus.INTERRUPTED.value,
                            updated_run.model_dump_json(),
                            run.run_id,
                        ),
                    )
                    db.execute(
                        "UPDATE tasks SET status=?, entity_version=entity_version+1, payload=? WHERE task_id=?",
                        (
                            TaskStatus.INTERRUPTED.value,
                            updated_task.model_dump_json(),
                            task.task_id,
                        ),
                    )
                    revision = self._next_revision(db)
                    self._append_event(
                        db,
                        task.owner_id,
                        revision,
                        "run.interrupted",
                        task.task_id,
                        run.run_id,
                    )
                    reconciled.append(run.run_id)
                db.execute("DELETE FROM runtime_leases WHERE run_id=?", (run.run_id,))
            return reconciled

        return await self.database.write(write)

    async def lease_count(self) -> int:
        return await self.database.read(
            lambda db: int(db.execute("SELECT COUNT(*) FROM runtime_leases").fetchone()[0])
        )

    async def has_lease(self, run_id: str) -> bool:
        return await self.database.read(
            lambda db: (
                db.execute("SELECT 1 FROM runtime_leases WHERE run_id=?", (run_id,)).fetchone()
                is not None
            )
        )

    async def record_trace(
        self,
        *,
        correlation_id: str,
        phase: str,
        now: datetime,
        message_id: str | None = None,
        task_id: str | None = None,
        run_id: str | None = None,
        duration_ms: float | None = None,
        fields: dict[str, object] | None = None,
        secrets: tuple[str, ...] = (),
    ) -> TraceRecord:
        trace = TraceRecord(
            trace_id=f"trace-{uuid.uuid4()}",
            correlation_id=correlation_id,
            message_id=message_id,
            task_id=task_id,
            run_id=run_id,
            phase=phase,
            timestamp=now,
            duration_ms=duration_ms,
            fields=redact_value(fields or {}, secrets),
        )
        await self.database.write(
            lambda db: db.execute(
                "INSERT INTO traces(trace_id, correlation_id, message_id, task_id, run_id, phase, timestamp, duration_ms, fields_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    trace.trace_id,
                    trace.correlation_id,
                    trace.message_id,
                    trace.task_id,
                    trace.run_id,
                    trace.phase,
                    trace.timestamp.isoformat(),
                    trace.duration_ms,
                    json.dumps(trace.fields, sort_keys=True),
                ),
            )
        )
        return trace

    async def traces(self, correlation_id: str) -> list[TraceRecord]:
        def read(db: sqlite3.Connection) -> list[TraceRecord]:
            return [
                TraceRecord(
                    trace_id=row["trace_id"],
                    correlation_id=row["correlation_id"],
                    message_id=row["message_id"],
                    task_id=row["task_id"],
                    run_id=row["run_id"],
                    phase=row["phase"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    duration_ms=row["duration_ms"],
                    fields=json.loads(row["fields_json"]),
                )
                for row in db.execute(
                    "SELECT * FROM traces WHERE correlation_id=? ORDER BY timestamp, rowid",
                    (correlation_id,),
                )
            ]

        return await self.database.read(read)

    async def pending_outbox(self, limit: int = 100) -> list[OutboxRecord]:
        return await self.database.read(
            lambda db: [
                OutboxRecord(event_id=str(row[0]), payload=str(row[1]))
                for row in db.execute(
                    "SELECT events.event_id, events.payload FROM outbox JOIN events USING(event_id) WHERE outbox.delivered_at IS NULL ORDER BY events.stream_id, events.sequence LIMIT ?",
                    (limit,),
                )
            ]
        )

    async def mark_outbox_delivered(self, event_id: str, now: datetime) -> None:
        await self.database.write(
            lambda db: db.execute(
                "UPDATE outbox SET delivered_at=?, attempts=attempts+1 WHERE event_id=?",
                (now.isoformat(), event_id),
            )
        )

    @staticmethod
    def _task(db: sqlite3.Connection, task_id: str) -> TaskRecord:
        row = db.execute("SELECT payload FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise LookupError(f"task {task_id} does not exist")
        return TaskRecord.model_validate_json(row[0])

    @staticmethod
    def _run(db: sqlite3.Connection, run_id: str) -> AgentRunRecord:
        row = db.execute("SELECT payload FROM agent_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise LookupError(f"run {run_id} does not exist")
        return AgentRunRecord.model_validate_json(row[0])

    @staticmethod
    def _revision(db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0])

    @staticmethod
    def _next_revision(db: sqlite3.Connection) -> int:
        return SoraRepository._next_revision(db)

    @staticmethod
    def _append_event(
        db: sqlite3.Connection,
        owner_id: str,
        revision: int,
        event_type: str,
        task_id: str | None,
        run_id: str | None,
    ) -> str:
        return SoraRepository._append_event(db, owner_id, revision, event_type, task_id, run_id)
