from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.identity.loader import IDENTITY_FILES, load_identity
from sora.persistence.backup import create_backup, restore_backup
from sora.persistence.database import SQLiteDatabase
from sora.persistence.records import MemoryState
from sora.persistence.repository import SoraRepository

from .helpers import sample_message, sample_task

NOW = datetime(2026, 9, 7, 17, 0, tzinfo=UTC)
IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_identity_uses_all_files_and_survives_provider_independent_restart(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sora.db"
    database = SQLiteDatabase(path)
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    bundle = load_identity(IDENTITY_ROOT)

    activated = await repository.activate_identity("owner-local", bundle, source="repository")
    reopened = SoraRepository(SQLiteDatabase(path))
    await reopened.database.initialize()
    restored = await reopened.active_identity("owner-local")

    assert restored == activated
    assert set(restored.files if restored else ()) == set(IDENTITY_FILES)
    assert "provider" not in activated.model_fields_set


@pytest.mark.asyncio
async def test_expired_corrected_and_deleted_memories_remain_labeled(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.add_memory(
        memory_id="memory-expired",
        owner_id="owner-local",
        project_id="project-sora",
        content="An old preference",
        scope="project",
        sensitivity="normal",
        retention="durable",
        provenance="user message",
        valid_until=NOW - timedelta(seconds=1),
    )
    await repository.add_memory(
        memory_id="memory-original",
        owner_id="owner-local",
        project_id="project-sora",
        content="The project is Ava",
        scope="project",
        sensitivity="normal",
        retention="durable",
        provenance="legacy import",
    )
    await repository.correct_memory(
        "memory-original",
        replacement_id="memory-corrected",
        content="The project is SORA",
        provenance="owner correction",
    )
    await repository.delete_memory("memory-corrected", deleted_at=NOW)

    all_records = await repository.list_memories(
        "owner-local", project_id="project-sora", observed_at=NOW, include_inactive=True
    )
    states = {item.memory_id: item.state for item in all_records}

    assert states == {
        "memory-expired": MemoryState.EXPIRED,
        "memory-original": MemoryState.SUPERSEDED,
        "memory-corrected": MemoryState.DELETED,
    }
    assert (
        await repository.list_memories("owner-local", project_id="project-sora", observed_at=NOW)
        == []
    )


@pytest.mark.asyncio
async def test_backup_restore_validates_database_and_artifacts_but_excludes_secrets(
    tmp_path: Path,
) -> None:
    database = SQLiteDatabase(tmp_path / "live" / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.register_conversation("conversation-001", "owner-local", "project-sora")
    await repository.append_message(sample_message())
    identity = await repository.activate_identity(
        "owner-local", load_identity(IDENTITY_ROOT), source="repository"
    )
    await repository.create_task(sample_task())
    artifacts = tmp_path / "live" / "artifacts"
    artifacts.mkdir()
    (artifacts / "result.txt").write_text("verified artifact", encoding="utf-8")
    (artifacts / "secrets").mkdir()
    (artifacts / "secrets" / "token.txt").write_text("fixture-secret", encoding="utf-8")

    backup = tmp_path / "backup"
    manifest = await create_backup(database, artifacts_root=artifacts, destination=backup)
    restore = tmp_path / "restore"
    await restore_backup(backup=backup, destination=restore)
    restored_database = SQLiteDatabase(restore / "data" / "sora.db")
    await restored_database.initialize()
    restored = SoraRepository(restored_database)

    assert manifest.is_file()
    assert await restored.get_task("task-001") == sample_task()
    assert await restored.list_messages("conversation-001") == [sample_message()]
    assert await restored.active_identity("owner-local") == identity
    assert (restore / "artifacts" / "result.txt").read_text() == "verified artifact"
    assert not (backup / "artifacts" / "secrets").exists()
    assert not (restore / "artifacts" / "secrets").exists()


@pytest.mark.asyncio
async def test_restore_rejects_manifest_path_escape(tmp_path: Path) -> None:
    database = SQLiteDatabase(tmp_path / "live.db")
    await database.initialize()
    backup = tmp_path / "backup"
    manifest_path = await create_backup(
        database, artifacts_root=tmp_path / "artifacts", destination=backup
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../outside.db"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe backup path"):
        await restore_backup(backup=backup, destination=tmp_path / "restore")
