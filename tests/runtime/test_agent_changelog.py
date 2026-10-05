"""Agent-authored changelog entries: what Core verifies, and what it refuses to author."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sora.runtime.agent_changelog import (
    MAX_ENTRY_BYTES,
    store_agent_entry,
    verify_agent_changelog,
)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _write_entry(root: Path, name: str, body: str) -> Path:
    path = root / "changelog" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_verifies_an_entry_inside_the_changelog_directory(tmp_path: Path) -> None:
    _write_entry(tmp_path, "20260929T120000_work_ANTIGRAVITY.md", "## Changed\n\n- a thing\n")
    verified = verify_agent_changelog(
        tmp_path, "changelog/20260929T120000_work_ANTIGRAVITY.md"
    )
    assert verified is not None
    assert verified.relative_path == "changelog/20260929T120000_work_ANTIGRAVITY.md"
    assert len(verified.sha256) == 64 and verified.bytes > 0 and verified.truncated is False


def test_windows_style_separators_are_accepted(tmp_path: Path) -> None:
    _write_entry(tmp_path, "entry.md", "body")
    assert verify_agent_changelog(tmp_path, "changelog\\entry.md") is not None


def test_absolute_paths_are_refused(tmp_path: Path) -> None:
    written = _write_entry(tmp_path, "entry.md", "body")
    assert verify_agent_changelog(tmp_path, str(written)) is None


def test_traversal_out_of_the_working_directory_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    (outside / "changelog").mkdir(parents=True)
    (outside / "changelog" / "escaped.md").write_text("body", encoding="utf-8")
    root = tmp_path / "work"
    root.mkdir()
    assert verify_agent_changelog(root, "../outside/changelog/escaped.md") is None


def test_files_outside_the_changelog_directory_are_refused(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("body", encoding="utf-8")
    assert verify_agent_changelog(tmp_path, "notes.md") is None


def test_empty_and_non_markdown_files_are_refused(tmp_path: Path) -> None:
    _write_entry(tmp_path, "empty.md", "   \n")
    _write_entry(tmp_path, "entry.txt", "body")
    assert verify_agent_changelog(tmp_path, "changelog/empty.md") is None
    assert verify_agent_changelog(tmp_path, "changelog/entry.txt") is None
    assert verify_agent_changelog(tmp_path, "") is None


def test_oversized_entries_are_marked_truncated(tmp_path: Path) -> None:
    _write_entry(tmp_path, "huge.md", "x" * (MAX_ENTRY_BYTES + 10))
    verified = verify_agent_changelog(tmp_path, "changelog/huge.md")
    assert verified is not None
    assert verified.truncated is True
    assert verified.bytes == MAX_ENTRY_BYTES


def test_store_agent_entry_keeps_the_agents_words_verbatim(tmp_path: Path) -> None:
    entry = store_agent_entry(
        tmp_path,
        agent="hermes-acp",
        task_id="task-42",
        entry="## Changed\n\n- nothing on disk\n",
        now=NOW,
    )
    body = entry.read_text(encoding="utf-8")
    assert entry.name == "20260929T120000_task-42_HERMES-ACP.md"
    assert "## Changed\n\n- nothing on disk" in body
    assert "stored here verbatim by Core" in body
