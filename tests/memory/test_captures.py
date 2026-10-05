"""Capture files: full detail first, bounded, atomic, disposable."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sora.memory.captures import (
    CaptureRecord,
    compact_captures,
    list_captures,
    read_capture,
    write_capture,
)

CREATED = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _record(**overrides: object) -> CaptureRecord:
    values: dict[str, object] = {
        "capture_id": "capture-1",
        "memory_id": "memory-1",
        "created_at": CREATED,
        "owner_id": "owner-local",
        "project_id": "project-sora",
        "provider": "openai-compatible",
        "model": "gemma-4-e2b",
        "owner_text": "My favourite colour is green.",
        "response_text": "Green it is - I'll remember that.",
        "rationale": "A lasting preference.",
        "reasoning": "She stated a stable fact about herself.",
    }
    values.update(overrides)
    return CaptureRecord.model_validate(values)


def test_capture_round_trips_the_full_detail(tmp_path: Path) -> None:
    path = write_capture(tmp_path, _record())
    stored = read_capture(path)
    assert stored is not None
    assert stored.owner_text == "My favourite colour is green."
    assert stored.response_text == "Green it is - I'll remember that."
    assert stored.rationale == "A lasting preference."
    assert stored.reasoning == "She stated a stable fact about herself."
    assert stored.compacted_at is None and stored.truncated is False
    assert path.name.endswith("-capture-1.json") and path.name.startswith("20260929T120000")


def test_capture_is_bounded_and_says_so(tmp_path: Path) -> None:
    path = write_capture(tmp_path, _record(response_text="x" * 200_000), max_bytes=8_192)
    stored = read_capture(path)
    assert stored is not None
    assert stored.truncated is True
    assert len(stored.response_text) < 200_000
    assert stored.owner_text.startswith("My favourite colour")
    assert path.stat().st_size <= 8_192 * 2


def test_capture_write_is_atomic(tmp_path: Path) -> None:
    write_capture(tmp_path, _record())
    write_capture(tmp_path, _record(capture_id="capture-2"))
    assert not list(tmp_path.glob(".capture-*"))
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_unreadable_capture_is_skipped_not_fatal(tmp_path: Path) -> None:
    write_capture(tmp_path, _record())
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert len(list_captures(tmp_path)) == 1
    assert read_capture(tmp_path / "broken.json") is None
    assert read_capture(tmp_path / "missing.json") is None


def test_compaction_marks_then_prunes_on_retention(tmp_path: Path) -> None:
    write_capture(tmp_path, _record())
    write_capture(
        tmp_path, _record(capture_id="capture-2", created_at=CREATED - timedelta(days=90))
    )
    first = compact_captures(tmp_path, now=CREATED, retention_days=30)
    assert first == {"marked": 2, "pruned": 0, "kept": 2}
    assert all(
        record.compacted_at is not None for _, record in list_captures(tmp_path)
    )
    later = CREATED + timedelta(days=31)
    second = compact_captures(tmp_path, now=later, retention_days=30)
    assert second["pruned"] == 2 and second["marked"] == 0
    assert list_captures(tmp_path) == []


def test_missing_root_is_an_empty_pass(tmp_path: Path) -> None:
    missing = tmp_path / "captures"
    assert list_captures(missing) == []
    assert compact_captures(missing, now=CREATED, retention_days=30) == {
        "marked": 0, "pruned": 0, "kept": 0,
    }
