"""Atomic owner-local lifecycle; exact-record forgetting, no capture/file erasure."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from typing import Literal, cast

from sora.contracts.memory_browser import MemoryCorrection, MemoryForget, MemoryMutationAck
from sora.persistence.records import MemoryState
from sora.persistence.repository import SoraRepository
from sora.runtime.memory_browser import MemoryProjectionError, _identifier

RETENTION_NOTE = (
    "Only this exact canonical record is affected. Correction supersedes it; forgetting "
    "soft-deletes it from retrieval and browsing. Other versions/successors are not forgotten. "
    "Private captures follow existing compaction/retention; conversation, audit, backups and "
    "agent transcripts are not erased. No Undo or physical-erasure guarantee. A receipt is "
    "historical confirmation, not proof of the record's current state."
)


class MemoryMutationConflict(Exception):
    def __init__(self, code: str, *, version: int | None = None, state: str | None = None):
        super().__init__(code)
        self.code = code
        self.version = version
        self.state = state


def _receipt(
    db: sqlite3.Connection, owner: str, project: str | None, request_id: uuid.UUID
) -> sqlite3.Row | None:
    row = db.execute(
        "SELECT request_hash, payload FROM memory_mutation_receipts "
        "WHERE owner_id=? AND project_scope=? AND request_id=?",
        (owner, project or "", str(request_id)),
    ).fetchone()
    return cast(sqlite3.Row | None, row)


def receipt(
    db: sqlite3.Connection,
    *,
    owner: str,
    project: str | None,
    request_id: uuid.UUID,
    instance: str,
) -> MemoryMutationAck:
    row = _receipt(db, owner, project, request_id)
    if row is None:
        raise LookupError("No committed mutation receipt")
    try:
        result = MemoryMutationAck.model_validate_json(row["payload"])
    except ValueError:
        raise MemoryProjectionError("Invalid canonical receipt") from None
    return result.model_copy(update={"instance_id": uuid.UUID(instance), "replayed": True})


async def mutate(
    repository: SoraRepository,
    *,
    owner: str,
    project: str | None,
    memory_id: str,
    instance: str,
    request: MemoryForget | MemoryCorrection,
    observed_at: datetime | None = None,
) -> MemoryMutationAck:
    _identifier(memory_id)
    if str(request.instance_id) != instance:
        raise MemoryMutationConflict("CORE_INSTANCE_CHANGED")
    action: Literal["correct", "forget"] = (
        "correct" if isinstance(request, MemoryCorrection) else "forget"
    )
    content_hash = (
        hashlib.sha256(request.content.encode()).hexdigest()
        if isinstance(request, MemoryCorrection)
        else None
    )
    binding = json.dumps(
        [memory_id, action, request.expected_version, content_hash], separators=(",", ":")
    )
    request_hash = hashlib.sha256(binding.encode()).hexdigest()

    def write(db: sqlite3.Connection) -> MemoryMutationAck:
        previous = _receipt(db, owner, project, request.request_id)
        if previous is not None:
            if previous["request_hash"] != request_hash:
                raise MemoryMutationConflict("MEMORY_REQUEST_CONFLICT")
            return receipt(
                db, owner=owner, project=project, request_id=request.request_id, instance=instance
            )
        now = observed_at or datetime.now(UTC)  # Evaluate expiry inside the write transaction.
        row = db.execute(
            "SELECT * FROM memories WHERE memory_id=? AND owner_id=? "
            "AND (project_id IS NULL OR project_id=?) AND deleted_at IS NULL",
            (memory_id, owner, project),
        ).fetchone()
        if row is None:
            raise LookupError("Memory not found")
        try:
            current = repository._memory_from_row(row, now)
        except (ValueError, TypeError):
            raise MemoryProjectionError("Invalid canonical record") from None
        if current.entity_version != request.expected_version:
            raise MemoryMutationConflict(
                "MEMORY_VERSION_CONFLICT", version=current.entity_version, state=current.state.value
            )
        if action == "correct" and current.state != MemoryState.ACTIVE:
            raise MemoryMutationConflict(
                "MEMORY_STATE_CONFLICT", version=current.entity_version, state=current.state.value
            )
        successor = f"memory-{uuid.uuid4()}" if action == "correct" else None
        if isinstance(request, MemoryCorrection):
            # Old capture evidence describes old text, not the owner's new assertion.
            db.execute(
                "INSERT INTO memories(memory_id, owner_id, project_id, content, scope, "
                "sensitivity, "
                "retention, provenance, evidence_json, entity_version, valid_until) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, '[]', 1, ?)",
                (
                    successor,
                    owner,
                    row["project_id"],
                    request.content,
                    row["scope"],
                    row["sensitivity"],
                    row["retention"],
                    f"owner correction of {memory_id}; request {request.request_id}",
                    row["valid_until"],
                ),
            )
            db.execute(
                "UPDATE memories SET superseded_by=?, entity_version=entity_version+1 "
                "WHERE memory_id=?",
                (successor, memory_id),
            )
        else:
            db.execute(
                "UPDATE memories SET deleted_at=?, entity_version=entity_version+1 "
                "WHERE memory_id=?",
                (now.isoformat(), memory_id),
            )
        revision = repository._next_revision(db)
        event = repository._append_event(
            db,
            owner,
            revision,
            "memory.corrected" if successor else "memory.deleted",
            None,
            None,
            {
                "memory_id": memory_id,
                "request_id": str(request.request_id),
                "entity_version": current.entity_version + 1,
                "successor_id": successor,
            },
        )
        ack = MemoryMutationAck(
            instance_id=uuid.UUID(instance),
            committed_instance_id=uuid.UUID(instance),
            request_id=request.request_id,
            owner_id=owner,
            project_id=row["project_id"],
            memory_id=memory_id,
            action=action,
            expected_version=request.expected_version,
            entity_version=current.entity_version + 1,
            successor_id=successor,
            successor_version=1 if successor else None,
            content_sha256=content_hash,
            projection_revision=revision,
            event_id=event,
            committed_at=now,
            retention_note=RETENTION_NOTE,
        )
        db.execute(
            "INSERT INTO memory_mutation_receipts(owner_id, project_scope, request_id, "
            "request_hash, payload) VALUES (?, ?, ?, ?, ?)",
            (owner, project or "", str(request.request_id), request_hash, ack.model_dump_json()),
        )
        return ack

    return await repository.database.write(write)
