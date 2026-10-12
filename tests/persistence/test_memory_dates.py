"""Memories carry created and updated dates on every write path (migration 13 triggers)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository


@pytest.mark.asyncio
async def test_insert_correct_and_delete_are_dated(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    before = datetime.now(UTC) - timedelta(seconds=1)
    await repository.add_memory(
        memory_id="memory-a", owner_id="owner-local", project_id=None,
        content="My favourite colour is teal.", scope="dialogue", sensitivity="private",
        retention="durable", provenance="owner-stated (test)",
    )
    first = (await repository.list_memories("owner-local", project_id=None,
                                           observed_at=datetime.now(UTC)))[0]
    assert first.created_at is not None and first.created_at >= before
    assert first.updated_at == first.created_at
    await repository.correct_memory("memory-a", replacement_id="memory-b",
                                    content="My favourite colour is green.",
                                    provenance="owner correction")
    rows = {m.memory_id: m for m in await repository.list_memories(
        "owner-local", project_id=None, observed_at=datetime.now(UTC), include_inactive=True)}
    old, new = rows["memory-a"], rows["memory-b"]
    assert new.created_at is not None and new.created_at >= first.created_at
    assert old.updated_at is not None and old.updated_at >= old.created_at  # type: ignore[operator]
    await repository.delete_memory("memory-b", deleted_at=datetime.now(UTC))
    after = await repository.list_memories(
        "owner-local", project_id=None, observed_at=datetime.now(UTC), include_inactive=True)
    gone = {m.memory_id: m for m in after}["memory-b"]
    assert gone.updated_at is not None and gone.updated_at >= new.updated_at  # type: ignore[operator]
