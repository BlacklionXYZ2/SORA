"""SORA's goals: dated, closed with start and end dates, progress linked to memories, limited."""

from __future__ import annotations

from pathlib import Path

import pytest

from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from sora.runtime import goals as goals_module
from sora.runtime.goals import GoalError, GoalStore


async def store(tmp_path: Path) -> GoalStore:
    database = SQLiteDatabase(tmp_path / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    return GoalStore(repository, "owner-local", tmp_path / "self")


@pytest.mark.asyncio
async def test_goal_lifecycle_keeps_dates_history_and_a_readable_copy(tmp_path: Path) -> None:
    goals = await store(tmp_path)
    goal = await goals.add("Get better at reading his screen", "So I can help without asking",
                           actor="sora")
    assert goal.status == "active" and goal.created_at == goal.updated_at
    goal = await goals.note(goal.goal_id, "Read the error in his terminal correctly",
                            ("memory-1",), actor="sora")
    goal = await goals.revise(goal.goal_id, "Read small text on his screen reliably",
                              "More specific", actor="sora")
    closed = await goals.close(goal.goal_id, "achieved", "High vision detail fixed it",
                               actor="sora")
    assert closed.status == "achieved" and closed.closed_at is not None
    assert closed.created_at <= closed.closed_at  # start and end dates kept
    assert [e.kind for e in closed.events] == ["added", "progress", "revised", "achieved"]
    assert closed.events[1].memory_ids == ("memory-1",)
    assert await goals.goals() == []  # closed goals are not shown as active...
    assert [g.goal_id for g in await goals.goals(include_closed=True)] == [goal.goal_id]  # ...kept
    markdown = (tmp_path / "self/goals.md").read_text(encoding="utf-8")
    assert "## Closed" in markdown and "achieved" in markdown
    assert "Read small text on his screen reliably" in markdown
    with pytest.raises(GoalError, match="already closed"):
        await goals.note(goal.goal_id, "too late", (), actor="sora")


@pytest.mark.asyncio
async def test_limits_apply_to_her_changes_not_the_owners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(goals_module, "SORA_CHANGES_PER_DAY", 2)
    goals = await store(tmp_path)
    await goals.add("Learn his music taste", "To pick better playlists", actor="sora")
    await goals.add("Remember his friends' names", "They matter to him", actor="sora")
    with pytest.raises(GoalError, match="Enough goal changes for today"):
        await goals.add("A third goal today", "Too many changes", actor="sora")
    owner_goal = await goals.add("Help with A Level revision", "Exams in May", actor="owner")
    assert owner_goal.origin == "owner"
    with pytest.raises(GoalError, match="already active"):
        await goals.add("learn his music taste", "Duplicate", actor="owner")
