"""Repositories that commit canonical state and outbox events atomically."""

# ruff: noqa: E501 -- SQL statements stay whole for direct comparison with the schema.

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import Field

from sora.contracts.base import StrictModel
from sora.contracts.models import (
    AgentRunRecord,
    AgentSessionRecord,
    ApprovalRequest,
    CapabilityGrant,
    NormalizedResult,
    PatchEnvelope,
    ProposeFactOperation,
    ProposeMemoryOperation,
    TaskRecord,
    UpdateTaskMetadataOperation,
)
from sora.contracts.patches import PatchConflict, PatchDisposition
from sora.identity.loader import IdentityBundle

from .database import SQLiteDatabase
from .records import IdentityRevisionRecord, MemoryState, MessageRecord, StoredMemory


def _now() -> str:
    return datetime.now(UTC).isoformat()


class PatchCommit(StrictModel):
    disposition: PatchDisposition
    revision: int
    event_ids: tuple[str, ...] = ()
    conflicts: tuple[PatchConflict, ...] = Field(default_factory=tuple)


class RecordKind(StrEnum):
    TASK = "task"
    FACT = "fact"
    MEMORY = "memory"
    PROJECT = "project"
    CONVERSATION = "conversation"


class SoraRepository:
    def __init__(self, database: SQLiteDatabase):
        self.database = database

    async def register_owner(self, owner_id: str) -> int:
        def write(db: sqlite3.Connection) -> int:
            cursor = db.execute(
                "INSERT OR IGNORE INTO owners(owner_id, created_at) VALUES (?, ?)",
                (owner_id, _now()),
            )
            if cursor.rowcount == 0:
                return int(
                    db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
                )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "owner.created", None, None)
            return revision

        return await self.database.write(write)

    async def register_project(self, project_id: str, owner_id: str) -> int:
        def write(db: sqlite3.Connection) -> int:
            cursor = db.execute(
                "INSERT OR IGNORE INTO projects(project_id, owner_id, created_at) VALUES (?, ?, ?)",
                (project_id, owner_id, _now()),
            )
            if cursor.rowcount == 0:
                return int(
                    db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
                )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "project.created", None, None)
            return revision

        return await self.database.write(write)

    async def register_conversation(
        self, conversation_id: str, owner_id: str, project_id: str | None
    ) -> int:
        def write(db: sqlite3.Connection) -> int:
            cursor = db.execute(
                "INSERT OR IGNORE INTO conversations(conversation_id, owner_id, project_id, created_at) VALUES (?, ?, ?, ?)",
                (conversation_id, owner_id, project_id, _now()),
            )
            if cursor.rowcount == 0:
                return int(
                    db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
                )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "conversation.created", None, None)
            return revision

        return await self.database.write(write)

    async def append_message(self, message: MessageRecord) -> int:
        def write(db: sqlite3.Connection) -> int:
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
            revision = self._next_revision(db)
            self._append_event(db, message.owner_id, revision, "message.finalized", None, None)
            return revision

        return await self.database.write(write)

    async def list_messages(self, conversation_id: str) -> list[MessageRecord]:
        def read(db: sqlite3.Connection) -> list[MessageRecord]:
            rows = db.execute(
                "SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at, message_id",
                (conversation_id,),
            ).fetchall()
            return [
                MessageRecord(
                    message_id=row["message_id"],
                    conversation_id=row["conversation_id"],
                    owner_id=row["owner_id"],
                    project_id=row["project_id"],
                    role=row["role"],
                    content=row["content"],
                    provenance=row["provenance"],
                    sensitivity=row["sensitivity"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

        return await self.database.read(read)

    async def activate_identity(
        self,
        owner_id: str,
        bundle: IdentityBundle,
        *,
        source: str,
    ) -> IdentityRevisionRecord:
        def write(db: sqlite3.Connection) -> IdentityRevisionRecord:
            version = int(
                db.execute(
                    "SELECT COALESCE(MAX(version), 0) + 1 FROM identity_revisions WHERE owner_id=?",
                    (owner_id,),
                ).fetchone()[0]
            )
            activated_at = datetime.now(UTC)
            identity_id = f"identity-{uuid.uuid4()}"
            db.execute("UPDATE identity_revisions SET active=0 WHERE owner_id=?", (owner_id,))
            db.execute(
                "INSERT INTO identity_revisions(identity_revision_id, owner_id, version, content_hash, source, activated_at, files_json, active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    identity_id,
                    owner_id,
                    version,
                    bundle.content_hash,
                    source,
                    activated_at.isoformat(),
                    json.dumps(bundle.files, sort_keys=True),
                ),
            )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "identity.activated", None, None)
            return IdentityRevisionRecord(
                identity_revision_id=identity_id,
                owner_id=owner_id,
                version=version,
                content_hash=bundle.content_hash,
                source=source,
                activated_at=activated_at,
                files=bundle.files,
            )

        return await self.database.write(write)

    async def active_identity(self, owner_id: str) -> IdentityRevisionRecord | None:
        def read(db: sqlite3.Connection) -> IdentityRevisionRecord | None:
            row = db.execute(
                "SELECT * FROM identity_revisions WHERE owner_id=? AND active=1", (owner_id,)
            ).fetchone()
            if row is None:
                return None
            return IdentityRevisionRecord(
                identity_revision_id=row["identity_revision_id"],
                owner_id=row["owner_id"],
                version=row["version"],
                content_hash=row["content_hash"],
                source=row["source"],
                activated_at=datetime.fromisoformat(row["activated_at"]),
                files=json.loads(row["files_json"]),
            )

        return await self.database.read(read)

    async def add_memory(
        self,
        *,
        memory_id: str,
        owner_id: str,
        project_id: str | None,
        content: str,
        scope: str,
        sensitivity: str,
        retention: str,
        provenance: str,
        evidence_refs: tuple[str, ...] = (),
        valid_until: datetime | None = None,
    ) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT INTO memories(memory_id, owner_id, project_id, content, scope, sensitivity, retention, provenance, evidence_json, entity_version, valid_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    memory_id,
                    owner_id,
                    project_id,
                    content,
                    scope,
                    sensitivity,
                    retention,
                    provenance,
                    json.dumps(evidence_refs),
                    valid_until.isoformat() if valid_until else None,
                ),
            )
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "memory.created", None, None)
            return revision

        return await self.database.write(write)

    async def correct_memory(
        self,
        memory_id: str,
        *,
        replacement_id: str,
        content: str,
        provenance: str,
    ) -> int:
        def write(db: sqlite3.Connection) -> int:
            row = db.execute("SELECT * FROM memories WHERE memory_id=?", (memory_id,)).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise LookupError(f"active memory {memory_id} does not exist")
            db.execute(
                "INSERT INTO memories(memory_id, owner_id, project_id, content, scope, sensitivity, retention, provenance, evidence_json, entity_version, valid_until) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
                (
                    replacement_id,
                    row["owner_id"],
                    row["project_id"],
                    content,
                    row["scope"],
                    row["sensitivity"],
                    row["retention"],
                    provenance,
                    row["evidence_json"],
                    row["valid_until"],
                ),
            )
            db.execute(
                "UPDATE memories SET superseded_by=?, entity_version=entity_version+1 WHERE memory_id=?",
                (replacement_id, memory_id),
            )
            revision = self._next_revision(db)
            self._append_event(db, row["owner_id"], revision, "memory.corrected", None, None)
            return revision

        return await self.database.write(write)

    async def delete_memory(self, memory_id: str, *, deleted_at: datetime) -> int:
        def write(db: sqlite3.Connection) -> int:
            row = db.execute(
                "SELECT owner_id, deleted_at FROM memories WHERE memory_id=?", (memory_id,)
            ).fetchone()
            if row is None or row["deleted_at"] is not None:
                raise LookupError(f"active memory {memory_id} does not exist")
            db.execute(
                "UPDATE memories SET deleted_at=?, entity_version=entity_version+1 WHERE memory_id=?",
                (deleted_at.isoformat(), memory_id),
            )
            revision = self._next_revision(db)
            self._append_event(db, row["owner_id"], revision, "memory.deleted", None, None)
            return revision

        return await self.database.write(write)

    async def list_memories(
        self,
        owner_id: str,
        *,
        project_id: str | None,
        observed_at: datetime,
        include_inactive: bool = False,
    ) -> list[StoredMemory]:
        def read(db: sqlite3.Connection) -> list[StoredMemory]:
            rows = db.execute(
                "SELECT * FROM memories WHERE owner_id=? AND (project_id IS NULL OR project_id=?) ORDER BY rowid",
                (owner_id, project_id),
            ).fetchall()
            records = [self._memory_from_row(row, observed_at) for row in rows]
            return (
                records
                if include_inactive
                else [item for item in records if item.state is MemoryState.ACTIVE]
            )

        return await self.database.read(read)

    async def create_task(self, task: TaskRecord) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT INTO tasks(task_id, owner_id, project_id, status, entity_version, payload) VALUES (?, ?, ?, ?, 1, ?)",
                (
                    task.task_id,
                    task.owner_id,
                    task.project_id,
                    task.status.value,
                    task.model_dump_json(),
                ),
            )
            revision = self._next_revision(db)
            self._append_event(db, task.owner_id, revision, "task.created", task.task_id, None)
            return revision

        return await self.database.write(write)

    async def create_run(self, run: AgentRunRecord) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT INTO agent_runs(run_id, task_id, status, payload) VALUES (?, ?, ?, ?)",
                (run.run_id, run.task_id, run.status.value, run.model_dump_json()),
            )
            owner_id = self._owner_for_task(db, run.task_id)
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "run.created", run.task_id, run.run_id)
            return revision

        return await self.database.write(write)

    async def create_session(self, session: AgentSessionRecord) -> int:
        def write(db: sqlite3.Connection) -> int:
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
            owner_id = self._owner_for_task(db, session.task_id)
            revision = self._next_revision(db)
            self._append_event(db, owner_id, revision, "session.created", session.task_id, None)
            return revision

        return await self.database.write(write)

    async def record_result(self, result: NormalizedResult, owner_id: str) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT INTO normalized_results(result_id, task_id, run_id, payload, accepted_at) VALUES (?, ?, ?, ?, ?)",
                (
                    result.result_id,
                    result.task_id,
                    result.run_id,
                    result.model_dump_json(),
                    _now(),
                ),
            )
            revision = self._next_revision(db)
            self._append_event(
                db, owner_id, revision, "result.accepted", result.task_id, result.run_id
            )
            return revision

        return await self.database.write(write)

    async def save_approval(self, approval: ApprovalRequest) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT OR REPLACE INTO approvals(approval_id, owner_id, status, payload) VALUES (?, ?, ?, ?)",
                (
                    approval.approval_id,
                    approval.capability.owner_id,
                    approval.status.value,
                    approval.model_dump_json(),
                ),
            )
            revision = self._next_revision(db)
            self._append_event(
                db, approval.capability.owner_id, revision, "approval.saved", None, None
            )
            return revision

        return await self.database.write(write)

    async def save_grant(self, grant: CapabilityGrant) -> int:
        def write(db: sqlite3.Connection) -> int:
            db.execute(
                "INSERT OR REPLACE INTO grants(grant_id, owner_id, status, payload) VALUES (?, ?, ?, ?)",
                (grant.grant_id, grant.owner_id, grant.status.value, grant.model_dump_json()),
            )
            revision = self._next_revision(db)
            self._append_event(db, grant.owner_id, revision, "grant.saved", None, None)
            return revision

        return await self.database.write(write)

    async def get_grant(self, grant_id: str) -> CapabilityGrant | None:
        def read(db: sqlite3.Connection) -> CapabilityGrant | None:
            row = db.execute("SELECT payload FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
            return CapabilityGrant.model_validate_json(row[0]) if row else None

        return await self.database.read(read)

    async def get_task(self, task_id: str) -> TaskRecord | None:
        def read(db: sqlite3.Connection) -> TaskRecord | None:
            row = db.execute("SELECT payload FROM tasks WHERE task_id=?", (task_id,)).fetchone()
            return TaskRecord.model_validate_json(row[0]) if row else None

        return await self.database.read(read)

    async def counts(self) -> dict[str, int]:
        tables = (
            "messages",
            "tasks",
            "agent_runs",
            "agent_sessions",
            "facts",
            "memories",
            "normalized_results",
            "approvals",
            "grants",
            "events",
            "outbox",
        )

        def read(db: sqlite3.Connection) -> dict[str, int]:
            return {
                table: int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in tables
            }

        return await self.database.read(read)

    async def revision(self) -> int:
        return await self.database.read(
            lambda db: int(
                db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
            )
        )

    async def apply_patch(self, patch: PatchEnvelope, owner_id: str) -> PatchCommit:
        return await self.database.write(lambda db: self._apply_patch(db, patch, owner_id))

    def _apply_patch(
        self,
        db: sqlite3.Connection,
        patch: PatchEnvelope,
        owner_id: str,
    ) -> PatchCommit:
        source = db.execute(
            "SELECT tasks.owner_id, tasks.project_id FROM agent_runs JOIN tasks ON tasks.task_id=agent_runs.task_id WHERE agent_runs.run_id=?",
            (patch.source_run_id,),
        ).fetchone()
        if source is None:
            raise LookupError(f"source run {patch.source_run_id} does not exist")
        if source["owner_id"] != owner_id:
            raise PermissionError("patch owner does not match its source task")
        expected_scope = (
            owner_id if source["project_id"] is None else f"{owner_id}/{source['project_id']}"
        )
        if patch.scope != expected_scope:
            raise PermissionError("patch scope does not match its source task")
        project_id = source["project_id"]

        duplicate = db.execute(
            "SELECT disposition FROM patches WHERE idempotency_key=?",
            (patch.idempotency_key,),
        ).fetchone()
        current_revision = int(
            db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
        )
        if duplicate:
            return PatchCommit(disposition=PatchDisposition.DUPLICATE, revision=current_revision)

        conflicts = tuple(
            conflict
            for precondition in patch.preconditions
            if (
                conflict := self._precondition_conflict(
                    db,
                    precondition.entity_type,
                    precondition.entity_id,
                    precondition.expected_version,
                )
            )
            is not None
        )
        if conflicts:
            db.execute(
                "INSERT INTO patches(patch_id, run_id, idempotency_key, disposition, payload, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    patch.patch_id,
                    patch.source_run_id,
                    patch.idempotency_key,
                    PatchDisposition.CONFLICT.value,
                    patch.model_dump_json(),
                    _now(),
                ),
            )
            revision = self._next_revision(db)
            event_id = self._append_event(
                db, owner_id, revision, "patch.conflicted", None, patch.source_run_id
            )
            return PatchCommit(
                disposition=PatchDisposition.CONFLICT,
                revision=revision,
                event_ids=(event_id,),
                conflicts=conflicts,
            )

        for operation in patch.operations:
            if isinstance(operation, ProposeFactOperation):
                db.execute(
                    "INSERT INTO facts(fact_id, owner_id, project_id, content, epistemic_status, confidence, provenance, evidence_json, entity_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        operation.operation_id,
                        owner_id,
                        project_id,
                        operation.fact.content,
                        operation.fact.epistemic_status,
                        operation.fact.confidence,
                        patch.provenance,
                        json.dumps(operation.fact.evidence_refs),
                    ),
                )
            elif isinstance(operation, ProposeMemoryOperation):
                db.execute(
                    "INSERT INTO memories(memory_id, owner_id, project_id, content, scope, sensitivity, retention, provenance, evidence_json, entity_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (
                        operation.operation_id,
                        owner_id,
                        project_id,
                        operation.memory.content,
                        operation.memory.scope,
                        operation.memory.sensitivity,
                        operation.memory.retention,
                        patch.provenance,
                        json.dumps(operation.memory.evidence_refs),
                    ),
                )
            elif isinstance(operation, UpdateTaskMetadataOperation):
                row = db.execute(
                    "SELECT payload, entity_version FROM tasks WHERE task_id=?",
                    (operation.task_id,),
                ).fetchone()
                if row is None:
                    raise LookupError(f"task {operation.task_id} does not exist")
                task = TaskRecord.model_validate_json(row["payload"])
                updated = task.model_copy(
                    update={"constraints": (*task.constraints, operation.summary)}
                )
                db.execute(
                    "UPDATE tasks SET payload=?, entity_version=? WHERE task_id=?",
                    (updated.model_dump_json(), int(row["entity_version"]) + 1, operation.task_id),
                )

        db.execute(
            "INSERT INTO patches(patch_id, run_id, idempotency_key, disposition, payload, recorded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                patch.patch_id,
                patch.source_run_id,
                patch.idempotency_key,
                PatchDisposition.APPLICABLE.value,
                patch.model_dump_json(),
                _now(),
            ),
        )
        revision = self._next_revision(db)
        event_id = self._append_event(
            db, owner_id, revision, "patch.applied", None, patch.source_run_id
        )
        return PatchCommit(
            disposition=PatchDisposition.APPLICABLE,
            revision=revision,
            event_ids=(event_id,),
        )

    @staticmethod
    def _owner_for_task(db: sqlite3.Connection, task_id: str) -> str:
        row = db.execute("SELECT owner_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise LookupError(f"task {task_id} does not exist")
        return str(row[0])

    @staticmethod
    def _memory_from_row(row: sqlite3.Row, observed_at: datetime) -> StoredMemory:
        valid_until = datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None
        deleted_at = datetime.fromisoformat(row["deleted_at"]) if row["deleted_at"] else None
        if deleted_at is not None:
            state = MemoryState.DELETED
        elif row["superseded_by"] is not None:
            state = MemoryState.SUPERSEDED
        elif valid_until is not None and observed_at >= valid_until:
            state = MemoryState.EXPIRED
        else:
            state = MemoryState.ACTIVE
        return StoredMemory(
            memory_id=row["memory_id"],
            owner_id=row["owner_id"],
            project_id=row["project_id"],
            content=row["content"],
            scope=row["scope"],
            sensitivity=row["sensitivity"],
            retention=row["retention"],
            provenance=row["provenance"],
            evidence_refs=tuple(json.loads(row["evidence_json"])),
            entity_version=row["entity_version"],
            state=state,
            valid_until=valid_until,
            superseded_by=row["superseded_by"],
            deleted_at=deleted_at,
        )

    @staticmethod
    def _precondition_conflict(
        db: sqlite3.Connection,
        entity_type: str,
        entity_id: str,
        expected: int,
    ) -> PatchConflict | None:
        table = {"task": "tasks", "fact": "facts", "memory": "memories"}.get(entity_type)
        if table is None:
            return PatchConflict(
                entity_type=entity_type,
                entity_id=entity_id,
                expected_version=expected,
                actual_version=None,
            )
        id_column = {"tasks": "task_id", "facts": "fact_id", "memories": "memory_id"}[table]
        row = db.execute(
            f"SELECT entity_version FROM {table} WHERE {id_column}=?", (entity_id,)
        ).fetchone()
        actual = int(row[0]) if row else None
        if actual == expected:
            return None
        return PatchConflict(
            entity_type=entity_type,
            entity_id=entity_id,
            expected_version=expected,
            actual_version=actual,
        )

    @staticmethod
    def _next_revision(db: sqlite3.Connection) -> int:
        db.execute("UPDATE state_meta SET revision=revision+1 WHERE singleton=1")
        return int(db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0])

    @staticmethod
    def _append_event(
        db: sqlite3.Connection,
        owner_id: str,
        revision: int,
        event_type: str,
        task_id: str | None,
        run_id: str | None,
    ) -> str:
        sequence = int(
            db.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE stream_id=?", (owner_id,)
            ).fetchone()[0]
        )
        event_id = f"event-{uuid.uuid4()}"
        payload = {
            "schema_version": "1.0",
            "event_id": event_id,
            "stream_id": owner_id,
            "sequence": sequence,
            "timestamp": _now(),
            "owner_id": owner_id,
            "source": "core",
            "event_type": event_type,
            "task_id": task_id,
            "run_id": run_id,
            "correlation_id": task_id or run_id or event_id,
            "revision": revision,
            "payload": {},
        }
        db.execute(
            "INSERT INTO events(event_id, stream_id, sequence, revision, payload) VALUES (?, ?, ?, ?, ?)",
            (event_id, owner_id, sequence, revision, json.dumps(payload)),
        )
        db.execute("INSERT INTO outbox(event_id, available_at) VALUES (?, ?)", (event_id, _now()))
        return event_id
