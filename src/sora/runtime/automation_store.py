"""Versioned canonical definitions/receipts/reservations, not a scheduler or task executor."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import wraps
from typing import Any, Concatenate, Literal, cast
from zoneinfo import ZoneInfo

from sora.contracts.automation import AutomationDefinition, AutomationOccurrence, AutomationSlot
from sora.contracts.automation_api import (
    AutomationAck,
    AutomationChange,
    AutomationCreate,
    AutomationDetail,
    AutomationHistory,
    AutomationPage,
    AutomationRunNow,
    AutomationSummary,
    SchedulerState,
)
from sora.contracts.base import require_aware
from sora.persistence.repository import SoraRepository
from sora.runtime.automation_clock import missed_disposition, next_slot


class AutomationConflict(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class AutomationStorageError(RuntimeError):
    """Never include private stored fields in an error."""


def _id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
        raise ValueError("Invalid canonical Automation ID")
    return value


def _snapshot[**P, ResultT](
    read: Callable[Concatenate[AutomationStore, sqlite3.Connection, P], ResultT],
) -> Callable[Concatenate[AutomationStore, sqlite3.Connection, P], ResultT]:
    @wraps(read)
    def wrapped(
        self: AutomationStore, db: sqlite3.Connection, /, *args: P.args, **kwargs: P.kwargs
    ) -> ResultT:
        own = not db.in_transaction
        if own:
            db.execute("BEGIN")
        try:
            return read(self, db, *args, **kwargs)
        finally:
            if own:
                db.rollback()  # Read-only snapshot; never alter an enclosing write transaction.

    return wrapped


class AutomationStore:
    def __init__(
        self,
        repository: SoraRepository,
        owner: str,
        project: str | None,
        instance: str,
        *,
        scheduler_state: Callable[[], SchedulerState] = lambda: "unavailable",
    ):
        self.repository, self.owner, self.project = repository, owner, project
        self.instance = str(uuid.UUID(instance))
        self.cursor_key = os.urandom(32)
        self.scheduler_state = scheduler_state

    def _row(
        self, db: sqlite3.Connection, automation: str, *, deleted: bool = False
    ) -> sqlite3.Row:
        _id(automation)
        row = db.execute(
            "SELECT rowid AS ordinal,* FROM automation_definitions WHERE automation_id=? "
            "AND owner_id=? AND (project_id IS NULL OR project_id=?) "
            + ("" if deleted else "AND state!='deleted'"),
            (automation, self.owner, self.project),
        ).fetchone()
        if row is None:
            raise LookupError("Automation not found")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _decode(row: sqlite3.Row) -> tuple[AutomationDefinition, AutomationSlot | None]:
        try:
            if len(row["payload"]) > 65536 or (
                row["next_slot_json"] and len(row["next_slot_json"]) > 4096
            ):
                raise ValueError("Oversized canonical definition")
            definition = AutomationDefinition.model_validate_json(row["payload"])
            slot = (
                AutomationSlot.model_validate_json(row["next_slot_json"])
                if row["next_slot_json"]
                else None
            )
            if (
                definition.automation_id,
                definition.owner_id,
                definition.project_id,
                definition.entity_version,
                definition.state,
            ) != (
                row["automation_id"],
                row["owner_id"],
                row["project_id"],
                row["entity_version"],
                row["state"],
            ):
                raise ValueError("Inconsistent definition")
            if definition.state != "active" and slot is not None:
                raise ValueError("Inactive definition has a due slot")
            if slot is not None and slot.timezone != definition.spec.trigger.timezone:
                raise ValueError("Slot timezone differs from definition")
            return definition, slot
        except (ValueError, TypeError):
            raise AutomationStorageError("Invalid canonical Automation record") from None

    @staticmethod
    def _revision(db: sqlite3.Connection) -> int:
        return int(db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0])

    def _receipt(self, db: sqlite3.Connection, request: uuid.UUID) -> sqlite3.Row | None:
        return cast(
            sqlite3.Row | None,
            db.execute(
                "SELECT request_hash,payload FROM automation_mutation_receipts "
                "WHERE owner_id=? AND project_scope=? AND request_id=?",
                (self.owner, self.project or "", str(request)),
            ).fetchone(),
        )

    def receipt_in(self, db: sqlite3.Connection, request: uuid.UUID) -> AutomationAck:
        row = self._receipt(db, request)
        if row is None:
            raise LookupError("Automation receipt not found")
        try:
            if len(row["payload"]) > 131072:
                raise ValueError("Oversized canonical receipt")
            ack = AutomationAck.model_validate_json(row["payload"])
            if (
                ack.definition.owner_id != self.owner
                or ack.request_id != request
                or ack.definition.project_id not in {None, self.project}
            ):
                raise ValueError("Inconsistent receipt")
            return ack.model_copy(
                update={"instance_id": uuid.UUID(self.instance), "replayed": True}
            )
        except ValueError:
            raise AutomationStorageError("Invalid canonical Automation receipt") from None

    async def mutate(
        self,
        request: AutomationCreate | AutomationChange,
        automation: str | None = None,
        *,
        observed_at: datetime | None = None,
    ) -> AutomationAck:
        if str(request.instance_id) != self.instance:
            raise AutomationConflict("CORE_INSTANCE_CHANGED")
        create = isinstance(request, AutomationCreate)
        if create != (automation is None):
            raise ValueError("Automation mutation target does not match operation")
        body = request.model_dump(mode="json", exclude={"instance_id", "request_id"})
        digest = hashlib.sha256(
            json.dumps([automation, body], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

        def write(db: sqlite3.Connection) -> AutomationAck:
            previous = self._receipt(db, request.request_id)
            if previous is not None:
                if previous["request_hash"] != digest:
                    raise AutomationConflict("AUTOMATION_REQUEST_CONFLICT")
                return self.receipt_in(db, request.request_id)
            now = require_aware(observed_at or datetime.now(UTC), "observed_at").astimezone(UTC)
            action: Literal["create", "edit", "pause", "resume", "delete"]
            if isinstance(request, AutomationCreate):
                definition = AutomationDefinition(
                    automation_id="automation-" + str(uuid.uuid4()),
                    owner_id=self.owner,
                    project_id=self.project,
                    entity_version=1,
                    state=request.state,
                    spec=request.spec,
                    created_at=now,
                    updated_at=now,
                )
                action = "create"
            else:
                assert automation is not None
                old, old_slot = self._decode(self._row(db, automation))
                if old.entity_version != request.expected_version:
                    raise AutomationConflict("AUTOMATION_VERSION_CONFLICT")
                if (
                    request.action == "pause"
                    and old.state != "active"
                    or request.action == "resume"
                    and old.state != "paused"
                ):
                    raise AutomationConflict("AUTOMATION_STATE_CONFLICT")
                state = {"pause": "paused", "resume": "active", "delete": "deleted"}.get(
                    request.action, old.state
                )
                definition = AutomationDefinition.model_validate(
                    {
                        **old.model_dump(),
                        "state": state,
                        "spec": request.spec or old.spec,
                        "entity_version": old.entity_version + 1,
                        "updated_at": now,
                    }
                )
                action = request.action
            slot = next_slot(definition.spec.trigger, now) if definition.state == "active" else None
            if (
                not create
                and isinstance(request, AutomationChange)
                and request.action == "edit"
                and definition.state == "active"
                and definition.spec.trigger == old.spec.trigger
            ):
                slot = old_slot  # Label/behavior edits do not silently postpone the next slot.
            if create:
                db.execute(
                    "INSERT INTO automation_definitions(automation_id,owner_id,project_id,"
                    "entity_version,state,payload,next_slot_json) VALUES (?,?,?,?,?,?,?)",
                    (
                        definition.automation_id,
                        self.owner,
                        self.project,
                        definition.entity_version,
                        definition.state,
                        definition.model_dump_json(),
                        slot.model_dump_json() if slot else None,
                    ),
                )
            else:
                db.execute(
                    "UPDATE automation_definitions SET entity_version=?,state=?,payload=?,"
                    "next_slot_json=? WHERE automation_id=?",
                    (
                        definition.entity_version,
                        definition.state,
                        definition.model_dump_json(),
                        slot.model_dump_json() if slot else None,
                        definition.automation_id,
                    ),
                )
            revision = self.repository._next_revision(db)
            event = self.repository._append_event(
                db,
                self.owner,
                revision,
                "automation." + action,
                None,
                None,
                {
                    "automation_id": definition.automation_id,
                    "request_id": str(request.request_id),
                    "entity_version": definition.entity_version,
                    "state": definition.state,
                },
            )
            ack = AutomationAck(
                instance_id=uuid.UUID(self.instance),
                committed_instance_id=uuid.UUID(self.instance),
                request_id=request.request_id,
                action=action,
                definition=definition,
                next_slot=slot,
                projection_revision=revision,
                event_id=event,
                scheduler_state=self.scheduler_state(),
            )
            db.execute(
                "INSERT INTO automation_mutation_receipts(owner_id,project_scope,request_id,"
                "request_hash,payload) VALUES (?,?,?,?,?)",
                (
                    self.owner,
                    self.project or "",
                    str(request.request_id),
                    digest,
                    ack.model_dump_json(),
                ),
            )
            return ack

        return await self.repository.database.write(write)

    async def run_now(
        self, request: AutomationRunNow, automation: str, *, observed_at: datetime | None = None
    ) -> AutomationAck:
        if str(request.instance_id) != self.instance:
            raise AutomationConflict("CORE_INSTANCE_CHANGED")
        _id(automation)
        digest = hashlib.sha256(
            json.dumps(
                [
                    automation,
                    request.model_dump(mode="json", exclude={"instance_id", "request_id"}),
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

        def write(db: sqlite3.Connection) -> AutomationAck:
            previous = self._receipt(db, request.request_id)
            if previous is not None:
                if previous["request_hash"] != digest:
                    raise AutomationConflict("AUTOMATION_REQUEST_CONFLICT")
                return self.receipt_in(db, request.request_id)
            definition, scheduled = self._decode(self._row(db, automation))
            if definition.entity_version != request.expected_version:
                raise AutomationConflict("AUTOMATION_VERSION_CONFLICT")
            now = require_aware(observed_at or datetime.now(UTC), "observed_at").astimezone(UTC)
            state = self.scheduler_state()
            overlapping = (
                db.execute(
                    "SELECT 1 FROM automation_occurrences WHERE automation_id=? "
                    "AND status IN ('reserved','admitted','unknown') LIMIT 1",
                    (automation,),
                ).fetchone()
                is not None
            )
            status: Literal["reserved", "skipped", "blocked"] = (
                "skipped"
                if overlapping
                else "reserved"
                if state in {"running", "degraded"}
                else "blocked"
            )
            value = AutomationOccurrence(
                occurrence_id="occurrence-" + str(uuid.uuid4()),
                automation_id=automation,
                definition_version=definition.entity_version,
                origin="manual",
                slot=AutomationSlot(
                    slot_key="manual:" + str(request.request_id),
                    decision_at=now,
                    planned_local=now.astimezone(
                        ZoneInfo(definition.spec.trigger.timezone)
                    ).strftime("%Y-%m-%dT%H:%M"),
                    timezone=definition.spec.trigger.timezone,
                ),
                status=status,
                behavior=definition.spec.behavior,
                recorded_at=now,
                reason="skip_overlap"
                if overlapping
                else ("scheduler_unavailable" if status == "blocked" else None),
            )
            key = (
                "automation-manual-"
                + hashlib.sha256(
                    json.dumps(
                        [self.owner, self.project, automation, str(request.request_id)],
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
            )
            db.execute(
                "INSERT INTO automation_occurrences(occurrence_id,automation_id,"
                "definition_version,origin,slot_key,status,submission_key,payload) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    value.occurrence_id,
                    automation,
                    value.definition_version,
                    value.origin,
                    value.slot.slot_key,
                    value.status,
                    key,
                    value.model_dump_json(),
                ),
            )
            revision = self.repository._next_revision(db)
            event = self.repository._append_event(
                db,
                self.owner,
                revision,
                "automation.run_now",
                None,
                None,
                {
                    "automation_id": automation,
                    "request_id": str(request.request_id),
                    "occurrence_id": value.occurrence_id,
                    "definition_version": value.definition_version,
                    "origin": "manual",
                    "status": value.status,
                    "reason": value.reason,
                },
            )
            ack = AutomationAck(
                instance_id=uuid.UUID(self.instance),
                committed_instance_id=uuid.UUID(self.instance),
                request_id=request.request_id,
                action="run_now",
                definition=definition,
                next_slot=scheduled,
                occurrence=value,
                projection_revision=revision,
                event_id=event,
                scheduler_state=state,
                note="Historical manual request receipt, not task admission/completion. "
                "Inspect this occurrence's history for current outcome. "
                "Unadmitted manual requests expire after five minutes.",
            )
            db.execute(
                "INSERT INTO automation_mutation_receipts(owner_id,project_scope,request_id,"
                "request_hash,payload) VALUES (?,?,?,?,?)",
                (
                    self.owner,
                    self.project or "",
                    str(request.request_id),
                    digest,
                    ack.model_dump_json(),
                ),
            )
            return ack

        return await self.repository.database.write(write)

    @_snapshot
    def detail_in(self, db: sqlite3.Connection, automation: str) -> AutomationDetail:
        definition, slot = self._decode(self._row(db, automation))
        return AutomationDetail(
            instance_id=uuid.UUID(self.instance),
            projection_revision=self._revision(db),
            definition=definition,
            next_slot=slot,
            scheduler_state=self.scheduler_state(),
        )

    def _cursor(self, binding: list[Any], value: tuple[int, int] | None) -> str:
        raw = json.dumps([binding, value], separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw + hmac.digest(self.cursor_key, raw, "sha256")).decode()

    def _bounds(self, binding: list[Any], cursor: str | None, ceiling: int) -> tuple[int, int]:
        if cursor is None:
            return ceiling, ceiling + 1
        try:
            if len(cursor) > 4096:
                raise ValueError()
            decoded = base64.b64decode(cursor, altchars=b"-_", validate=True)
            raw, signature = decoded[:-32], decoded[-32:]
            if not hmac.compare_digest(hmac.digest(self.cursor_key, raw, "sha256"), signature):
                raise ValueError()
            encoded_binding, values = json.loads(raw)
            if encoded_binding != binding or not isinstance(values, list) or len(values) != 2:
                raise ValueError()
            top, before = values
            if type(top) is not int or type(before) is not int or not 0 <= before <= top <= ceiling:
                raise ValueError()
            return top, before
        except (ValueError, TypeError):
            raise ValueError("Invalid or stale Automation cursor") from None

    @_snapshot
    def page_in(
        self,
        db: sqlite3.Connection,
        *,
        query: str = "",
        state: str = "all",
        limit: int = 50,
        cursor: str | None = None,
    ) -> AutomationPage:
        if len(query) > 256 or state not in {"all", "active", "paused"} or not 1 <= limit <= 50:
            raise ValueError("Invalid bounded Automation filters")
        ceiling = int(
            db.execute("SELECT COALESCE(MAX(rowid),0) FROM automation_definitions").fetchone()[0]
        )
        binding = [self.instance, self.owner, self.project, "definitions", query, state, limit]
        top, before = self._bounds(binding, cursor, ceiling)
        rows = db.execute(
            "SELECT rowid AS ordinal,* FROM automation_definitions WHERE owner_id=? "
            "AND (project_id IS NULL OR project_id=?) AND state!='deleted' "
            "AND rowid<=? AND rowid<? ORDER BY rowid DESC",
            (self.owner, self.project, top, before),
        )
        selected: list[AutomationSummary] = []
        last = before
        # Bound scans as well as returned records; continuation admits no later rows.
        scanned = 0
        for row in rows:
            scanned += 1
            if scanned > 256:
                break
            last = int(row["ordinal"])
            definition, slot = self._decode(row)
            if (
                state != "all" and definition.state != state
            ) or query.casefold() not in definition.spec.name.casefold():
                continue
            selected.append(
                AutomationSummary(
                    automation_id=definition.automation_id,
                    name=definition.spec.name,
                    state=cast(Any, definition.state),
                    entity_version=definition.entity_version,
                    trigger_kind=definition.spec.trigger.kind,
                    timezone=definition.spec.trigger.timezone,
                    next_slot=slot,
                )
            )
            if len(selected) == limit:
                break
        more = (
            db.execute(
                "SELECT 1 FROM automation_definitions WHERE owner_id=? "
                "AND (project_id IS NULL OR project_id=?) "
                "AND state!='deleted' AND rowid<? AND rowid<=? LIMIT 1",
                (self.owner, self.project, last, top),
            ).fetchone()
            is not None
        )
        return AutomationPage(
            instance_id=uuid.UUID(self.instance),
            projection_revision=self._revision(db),
            observed_at=datetime.now(UTC),
            automations=tuple(selected),
            scheduler_state=self.scheduler_state(),
            next_cursor=self._cursor(binding, (top, last)) if more else None,
        )

    @_snapshot
    def history_in(
        self, db: sqlite3.Connection, automation: str, *, limit: int = 50, cursor: str | None = None
    ) -> AutomationHistory:
        self._decode(self._row(db, automation, deleted=True))
        if not 1 <= limit <= 50:
            raise ValueError("Invalid history page size")
        ceiling = int(
            db.execute("SELECT COALESCE(MAX(rowid),0) FROM automation_occurrences").fetchone()[0]
        )
        binding = [self.instance, self.owner, self.project, "history", automation, limit]
        top, before = self._bounds(binding, cursor, ceiling)
        rows = db.execute(
            "SELECT rowid AS ordinal,* FROM automation_occurrences WHERE automation_id=? "
            "AND rowid<=? AND rowid<? ORDER BY rowid DESC LIMIT ?",
            (automation, top, before, limit + 1),
        ).fetchall()
        results = tuple(self._occurrence(row) for row in rows[:limit])
        continuation = (
            self._cursor(binding, (top, int(rows[limit - 1]["ordinal"])))
            if len(rows) > limit
            else None
        )
        return AutomationHistory(
            instance_id=uuid.UUID(self.instance),
            projection_revision=self._revision(db),
            automation_id=automation,
            occurrences=results,
            next_cursor=continuation,
        )

    @staticmethod
    def _occurrence(row: sqlite3.Row) -> AutomationOccurrence:
        try:
            if len(row["payload"]) > 65536:
                raise ValueError("Oversized canonical occurrence")
            value = AutomationOccurrence.model_validate_json(row["payload"])
            if (
                value.occurrence_id,
                value.automation_id,
                value.definition_version,
                value.origin,
                value.slot.slot_key,
                value.status,
                value.task_id,
                value.run_id,
            ) != (
                row["occurrence_id"],
                row["automation_id"],
                row["definition_version"],
                row["origin"],
                row["slot_key"],
                row["status"],
                row["task_id"],
                row["run_id"],
            ):
                raise ValueError()
            return value
        except (ValueError, TypeError):
            raise AutomationStorageError("Invalid canonical Automation occurrence") from None

    async def reserve_scheduled(
        self, automation: str, version: int, slot_key: str, *, now: datetime, recovered: bool
    ) -> AutomationOccurrence | None:
        observed = require_aware(now, "now").astimezone(UTC)

        def write(db: sqlite3.Connection) -> AutomationOccurrence | None:
            definition, slot = self._decode(self._row(db, automation))
            if definition.entity_version != version or definition.state != "active":
                raise AutomationConflict("AUTOMATION_VERSION_STATE_CHANGED")
            previous = db.execute(
                "SELECT * FROM automation_occurrences WHERE automation_id=? "
                "AND definition_version=? AND origin='scheduled' AND slot_key=?",
                (automation, version, slot_key),
            ).fetchone()
            if previous is not None:
                return self._occurrence(previous)
            if slot is None or slot.slot_key != slot_key:
                raise AutomationConflict("AUTOMATION_SLOT_CHANGED")
            overlapping = (
                db.execute(
                    "SELECT 1 FROM automation_occurrences WHERE automation_id=? "
                    "AND status IN ('reserved','admitted','unknown') LIMIT 1",
                    (automation,),
                ).fetchone()
                is not None
            )
            disposition = missed_disposition(
                definition.spec, slot, observed, recovered=recovered, overlapping=overlapping
            )
            if disposition == "wait":
                return None
            value = AutomationOccurrence(
                occurrence_id="occurrence-" + str(uuid.uuid4()),
                automation_id=automation,
                definition_version=version,
                origin="scheduled",
                slot=slot,
                status="reserved" if disposition == "admit" else "skipped",
                behavior=definition.spec.behavior,
                reason=None if disposition == "admit" else disposition,
                recorded_at=observed,
            )
            submission_key = (
                "automation-"
                + hashlib.sha256(
                    (automation + "\n" + str(version) + "\n" + slot_key).encode()
                ).hexdigest()
            )
            db.execute(
                "INSERT INTO automation_occurrences(occurrence_id,automation_id,"
                "definition_version,origin,slot_key,status,submission_key,payload) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    value.occurrence_id,
                    automation,
                    version,
                    value.origin,
                    slot_key,
                    value.status,
                    submission_key,
                    value.model_dump_json(),
                ),
            )
            following = next_slot(definition.spec.trigger, max(observed, slot.decision_at))
            db.execute(
                "UPDATE automation_definitions SET next_slot_json=? WHERE automation_id=?",
                (following.model_dump_json() if following else None, automation),
            )
            revision = self.repository._next_revision(db)
            self.repository._append_event(
                db,
                self.owner,
                revision,
                "automation.occurrence.reserved"
                if value.status == "reserved"
                else "automation.occurrence.skipped",
                None,
                None,
                {
                    "automation_id": automation,
                    "occurrence_id": value.occurrence_id,
                    "definition_version": version,
                    "origin": value.origin,
                    "status": value.status,
                    "reason": value.reason,
                    "missed_until": observed.isoformat() if disposition == "skip_missed" else None,
                },
            )
            return value

        return await self.repository.database.write(write)
