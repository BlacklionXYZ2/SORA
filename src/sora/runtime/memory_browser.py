"""Bounded reads over canonical SQL memories; no model call or capture-file access."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import sqlite3
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from functools import lru_cache
from typing import cast

from sora.contracts.base import require_aware
from sora.contracts.content import ContentReference
from sora.contracts.memory_browser import (
    MemoryDetail,
    MemoryEvidence,
    MemoryFilterState,
    MemoryPage,
    MemoryProjectFilter,
    MemoryRecord,
    MemorySummary,
    VisibleMemoryState,
)

NOTE = (
    "Canonical owner-local records, not private capture rationale or reasoning. "
    "Literal content search (SQLite LIKE; ASCII case-insensitive), not semantic ranking. "
    "Newest storage admissions first, not a claimed creation date. Paging excludes later "
    "admissions until Refresh; existing states and counts are live at observed_at. Deleted "
    "records are absent. Active is storage state, not proof this record is in a model prompt. "
    "Only current scoped registered evidence is linked; paths and capture IDs are withheld."
)
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_STATE = (
    "CASE WHEN superseded_by IS NOT NULL THEN 'superseded' "
    "WHEN valid_until IS NOT NULL AND sora_memory_expired(valid_until) "
    "THEN 'expired' ELSE 'active' END"
)


class MemoryProjectionError(RuntimeError):
    """Invalid canonical record; do not echo private stored values in API errors."""


def _register_expiry(db: sqlite3.Connection, now: datetime) -> None:
    # Match StoredMemory's aware datetime comparison, including microseconds;
    # SQLite julianday rounds sub-millisecond boundaries. Bounded per-read cache.
    @lru_cache(maxsize=1024)
    def expired(value: str) -> bool:
        return require_aware(datetime.fromisoformat(value), "valid_until") <= now

    db.create_function("sora_memory_expired", 1, expired, deterministic=True)


def _identifier(value: str) -> None:
    if not _ID.fullmatch(value):
        raise ValueError("Invalid exact Memory identity")


def _filters(state: str, project: str, scope: str, query: str, limit: int) -> None:
    if (
        state not in {"active", "expired", "superseded", "all"}
        or project not in {"all", "project", "global"}
        or type(limit) is not int
        or not 1 <= limit <= 100
        or len(scope) > 128
        or len(query) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in scope + query)
    ):
        raise ValueError("Invalid bounded Memory filter")


def _binding(
    owner: str,
    project_id: str | None,
    instance: str,
    state: str,
    project: str,
    scope: str,
    query: str,
    limit: int,
) -> str:
    return hashlib.sha256(
        json.dumps([owner, project_id, instance, state, project, scope, query, limit]).encode()
    ).hexdigest()


def _cursor(binding: str, ceiling: int, before: int, key: bytes) -> str:
    payload = json.dumps([binding, ceiling, before], separators=(",", ":")).encode()
    return (
        base64.urlsafe_b64encode(payload + hmac.digest(key, payload, "sha256")).decode().rstrip("=")
    )


def _read_cursor(value: str, binding: str, max_ceiling: int, key: bytes) -> tuple[int, int]:
    try:
        if not 1 <= len(value) <= 1024 or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid cursor")
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        payload, signature = raw[:-32], raw[-32:]
        if not hmac.compare_digest(signature, hmac.digest(key, payload, "sha256")):
            raise ValueError("Invalid cursor signature")
        parts = json.loads(payload)
        if (
            not isinstance(parts, list)
            or len(parts) != 3
            or parts[0] != binding
            or type(parts[1]) is not int
            or type(parts[2]) is not int
            or not 1 <= parts[2] <= parts[1] <= max_ceiling
        ):
            raise ValueError("Cursor scope/bounds mismatch")
        return parts[1], parts[2]
    except (ValueError, TypeError, binascii.Error, UnicodeDecodeError) as error:
        raise ValueError("Invalid scope/filter/instance-bound Memory cursor") from error


def _revision(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0])


def _summary(row: sqlite3.Row) -> MemorySummary:
    try:
        metadata = {
            key: str(row[key]) for key in ("scope", "sensitivity", "retention", "provenance")
        }
        return MemorySummary(
            memory_id=row["memory_id"],
            owner_id=row["owner_id"],
            project_id=row["project_id"],
            entity_version=row["entity_version"],
            state=cast(VisibleMemoryState, row["visible_state"]),
            scope=metadata["scope"][:128],
            sensitivity=metadata["sensitivity"][:128],
            retention=metadata["retention"][:128],
            provenance=metadata["provenance"][:512],
            metadata_truncated=any(
                len(value) > (512 if key == "provenance" else 128)
                for key, value in metadata.items()
            ),
            content_preview=row["preview"][:512],
            content_truncated=row["content_length"] > 512,
            valid_until=datetime.fromisoformat(row["valid_until"]) if row["valid_until"] else None,
        )
    except (ValueError, TypeError) as error:
        raise MemoryProjectionError("Canonical Memory projection unavailable") from error


def memory_page(
    db: sqlite3.Connection,
    *,
    owner: str,
    project_id: str | None,
    instance: str,
    key: bytes,
    state: str = "active",
    project: str = "all",
    scope: str = "",
    query: str = "",
    limit: int = 50,
    cursor: str | None = None,
    observed_at: datetime | None = None,
) -> MemoryPage:
    _filters(state, project, scope, query, limit)
    _identifier(owner)
    if project_id is not None:
        _identifier(project_id)
    uuid.UUID(instance)
    now = require_aware(observed_at or datetime.now(UTC), "observed_at")
    _register_expiry(db, now)
    # Several reads must share a SQLite snapshot, even if a concurrent writer
    # changes retention/deletion between row retrieval and revision/count reads.
    started = not db.in_transaction
    if started:
        db.execute("BEGIN")
    try:
        where = "owner_id=? AND (project_id IS NULL OR project_id=?) AND deleted_at IS NULL"
        args: list[object] = [owner, project_id]
        ceiling = int(
            db.execute(
                "SELECT COALESCE(MAX(rowid),0) FROM memories WHERE owner_id=? "
                "AND (project_id IS NULL OR project_id=?)",
                args,
            ).fetchone()[0]
        )
        binding = _binding(owner, project_id, instance, state, project, scope, query, limit)
        before = ceiling + 1
        if cursor is not None:
            ceiling, before = _read_cursor(cursor, binding, ceiling, key)
        where += " AND rowid<=?"
        args.append(ceiling)
        if project != "all":
            where += " AND project_id IS NULL" if project == "global" else " AND project_id=?"
            if project == "project":
                args.append(project_id)
        if scope:
            where += " AND scope=?"
            args.append(scope)
        if query:
            where += " AND content LIKE ? ESCAPE '\\'"
            args.append(
                "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            )
        if state != "all":
            where += " AND (" + _STATE + ")=?"
            args.append(state)
        rows = db.execute(
            "SELECT rowid AS rowid_value,memory_id,owner_id,project_id,entity_version,valid_until, "
            "substr(scope,1,129) AS scope,substr(sensitivity,1,129) AS sensitivity, "
            "substr(retention,1,129) AS retention,substr(provenance,1,513) AS provenance, "
            "substr(content,1,512) AS preview, length(content) AS content_length, "
            + _STATE
            + " AS visible_state FROM memories WHERE "
            + where
            + " AND rowid<? ORDER BY rowid DESC LIMIT ?",
            [*args, before, limit + 1],
        ).fetchall()
        # Do not transfer full content/evidence into a page or deserialize scratchpads.
        items = tuple(_summary(row) for row in rows[:limit])
        return MemoryPage(
            instance_id=uuid.UUID(instance),
            owner_id=owner,
            project_id=project_id,
            projection_revision=_revision(db),
            observed_at=now,
            evidence_note=NOTE,
            state_filter=cast(MemoryFilterState, state),
            project_filter=cast(MemoryProjectFilter, project),
            scope_filter=scope,
            query=query,
            limit=limit,
            memories=items,
            total=int(
                db.execute("SELECT COUNT(*) FROM memories WHERE " + where, args).fetchone()[0]
            ),
            next_cursor=_cursor(binding, ceiling, int(rows[limit - 1]["rowid_value"]), key)
            if len(rows) > limit
            else None,
        )
    finally:
        if started:
            db.rollback()


def memory_detail(
    db: sqlite3.Connection,
    *,
    owner: str,
    project_id: str | None,
    memory_id: str,
    instance: str,
    device: str,
    references: Sequence[ContentReference] = (),
    observed_at: datetime | None = None,
) -> MemoryDetail:
    _identifier(memory_id)
    now = require_aware(observed_at or datetime.now(UTC), "observed_at")
    _register_expiry(db, now)
    started = not db.in_transaction
    if started:
        db.execute("BEGIN")
    try:
        row = db.execute(
            "SELECT memory_id,owner_id,project_id,entity_version,valid_until,superseded_by, "
            "substr(scope,1,129) AS scope,substr(sensitivity,1,129) AS sensitivity, "
            "substr(retention,1,129) AS retention,substr(provenance,1,513) AS provenance, "
            "substr(content,1,16385) AS content,substr(evidence_json,1,65537) AS evidence_json, "
            "substr(content,1,512) AS preview, length(content) AS content_length, "
            + _STATE
            + " AS visible_state FROM memories WHERE memory_id=? AND owner_id=? "
            "AND (project_id IS NULL OR project_id=?) AND deleted_at IS NULL",
            (memory_id, owner, project_id),
        ).fetchone()
        if row is None:
            raise LookupError("Memory not found")
        summary = _summary(row)
        evidence: list[MemoryEvidence] = []
        withheld = False
        raw = row["evidence_json"]
        permitted = {
            ref.reference_id: ref
            for ref in references
            if ref.owner_id == owner
            and ref.device_id == device
            and ref.project_id == project_id
            and not ref.reference_id.startswith("capture-")
        }
        if not isinstance(raw, str) or len(raw) > 65536:
            withheld = True
        else:
            try:
                refs = json.loads(raw)
                if not isinstance(refs, list):
                    raise ValueError("Invalid evidence")
                seen: set[str] = set()
                for ref_id in refs:
                    if (
                        not isinstance(ref_id, str)
                        or ref_id not in permitted
                        or ref_id in seen
                        or len(evidence) >= 64
                    ):
                        withheld = True
                        continue
                    seen.add(ref_id)
                    ref = permitted[ref_id]
                    evidence.append(
                        MemoryEvidence(reference_id=ref_id, label=ref.label[:512], kind=ref.kind)
                    )
            except (ValueError, TypeError):
                withheld = True
        successor = row["superseded_by"]
        if (
            successor
            and db.execute(
                "SELECT 1 FROM memories WHERE memory_id=? AND owner_id=? "
                "AND (project_id IS NULL OR project_id=?) AND deleted_at IS NULL",
                (successor, owner, project_id),
            ).fetchone()
            is None
        ):
            successor = None
        try:
            record = MemoryRecord(
                **summary.model_dump(),
                content=row["content"],
                superseded_by=successor,
                evidence=tuple(evidence),
                evidence_withheld=withheld,
            )
        except ValueError as error:
            raise MemoryProjectionError("Canonical Memory detail unavailable") from error
        return MemoryDetail(
            instance_id=uuid.UUID(instance),
            owner_id=owner,
            project_id=project_id,
            projection_revision=_revision(db),
            observed_at=now,
            evidence_note=NOTE,
            memory=record,
        )
    finally:
        if started:
            db.rollback()
