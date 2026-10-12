"""Full-detail capture files: written when SORA chooses to remember, compressed into SQL later.

A capture is staging, never a second source of truth. It holds the owner's message, the whole
model response and, when the model produced one, her stated rationale and thinking - so nothing
important has to be summarised at the moment of remembering. Canonical memory always lives in the
`memories` table; a capture exists to be compacted and then pruned on retention.

Boundaries that make captures safe to keep:

* write-only - a capture is never fed back into a prompt, a status file, an activity summary or
  any social payload (that is how "no hidden chain-of-thought is exposed" survives having a file
  at all);
* bounded - a single capture is capped and marked ``truncated`` rather than silently cut;
* atomic - written to a temporary file and renamed, so a crash never leaves a half-written capture;
* disposable - compaction marks it, retention deletes it, and an unreadable file is skipped rather
  than allowed to break a maintenance pass.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import Field

from sora.contracts.base import StrictModel


class CaptureRecord(StrictModel):
    """One remembered moment, captured in full before any compression happens."""

    capture_id: str = Field(min_length=1, max_length=128)
    memory_id: str | None = Field(default=None, max_length=128)
    created_at: datetime
    owner_id: str = Field(min_length=1, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=256)
    owner_text: str = Field(min_length=1)
    response_text: str
    rationale: str | None = None
    reasoning: str | None = None
    sensitivity: str = Field(default="private", max_length=32)
    truncated: bool = False
    compacted_at: datetime | None = None


def _bounded(record: CaptureRecord, max_bytes: int) -> CaptureRecord:
    """Keep the size promise honestly: shrink the two long fields and say that it happened."""
    payload = record.model_dump_json()
    if len(payload.encode("utf-8")) <= max_bytes:
        return record
    owner_budget = max(1, max_bytes // 6)
    response_budget = max(1, (max_bytes * 2) // 3)
    return record.model_copy(
        update={
            "owner_text": record.owner_text[:owner_budget],
            "response_text": record.response_text[:response_budget],
            "rationale": None,
            "reasoning": None,
            "truncated": True,
        }
    )


def write_capture(root: Path, record: CaptureRecord, *, max_bytes: int = 65_536) -> Path:
    """Write one capture atomically and return its path."""
    root.mkdir(parents=True, exist_ok=True)
    bounded = _bounded(record, max_bytes)
    payload = bounded.model_dump_json(indent=2)
    stamp = bounded.created_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S")
    target = root / f"{stamp}-{bounded.capture_id}.json"
    handle_fd, temporary = tempfile.mkstemp(dir=root, prefix=".capture-", suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


def read_capture(path: Path) -> CaptureRecord | None:
    """Read one capture; an unreadable file returns None instead of raising."""
    try:
        return CaptureRecord.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_captures(root: Path) -> list[tuple[Path, CaptureRecord]]:
    """All readable captures, oldest first. Unreadable entries are skipped, never fatal."""
    if not root.exists():
        return []
    items: list[tuple[Path, CaptureRecord]] = []
    for path in sorted(root.glob("*.json")):
        record = read_capture(path)
        if record is not None:
            items.append((path, record))
    return items


def compact_captures(root: Path, *, now: datetime, retention_days: int) -> dict[str, int]:
    """Mark folded captures, then prune those past retention.

    Compaction is deliberately deterministic: the canonical row is already written when a moment is
    remembered, so this pass is the capture's lifecycle - mark it folded, then delete it once its
    retention window closes. Model-assisted distillation, if it is ever wanted, plugs in here.
    """
    marked = 0
    pruned = 0
    kept = 0
    cutoff = now - timedelta(days=retention_days)
    for path, record in list_captures(root):
        if record.compacted_at is None:
            updated = record.model_copy(update={"compacted_at": now})
            try:
                path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
            except OSError:
                kept += 1
                continue
            record = updated
            marked += 1
        if record.compacted_at is not None and record.compacted_at < cutoff:
            try:
                path.unlink()
            except OSError:
                kept += 1
                continue
            pruned += 1
        else:
            kept += 1
    return {"marked": marked, "pruned": pruned, "kept": kept}


def capture_dates(root: Path) -> dict[str, datetime]:
    """When each captured memory was made: dates memories stored before they carried dates."""
    return {record.memory_id: record.created_at for _, record in list_captures(root)
            if record.memory_id}
