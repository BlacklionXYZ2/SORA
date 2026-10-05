"""Managed SORA state-slot backup, restore, initialization, and integrity checks."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from sora.identity.loader import load_identity
from sora.persistence.backup import create_backup, restore_backup
from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository


async def initialize_state(
    root: Path,
    *,
    identity_root: Path,
    owner_id: str = "owner-local",
    project_id: str = "project-sora",
    conversation_id: str = "conversation-main",
) -> dict[str, Any]:
    """Create a canonical empty state slot without starting providers or listeners."""

    state_root = root.resolve()
    database = SQLiteDatabase(state_root / "data" / "sora.db")
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner(owner_id)
    await repository.register_project(project_id, owner_id)
    await repository.register_conversation(conversation_id, owner_id, project_id)
    if await repository.active_identity(owner_id) is None:
        await repository.activate_identity(owner_id, load_identity(identity_root), source="release")
    return await verify_state(state_root, migrate=False)


async def backup_state(root: Path, destination: Path) -> Path:
    state_root = root.resolve(strict=True)
    database = SQLiteDatabase(state_root / "data" / "sora.db")
    await _require_healthy_database(database, migrate=False)
    return await create_backup(
        database,
        artifacts_root=state_root / ".local" / "artifacts",
        destination=destination,
        artifacts_archive_prefix=".local/artifacts",
    )


async def restore_state(backup: Path, destination: Path) -> dict[str, Any]:
    await restore_backup(backup=backup, destination=destination)
    return await verify_state(destination, migrate=True)


async def _require_healthy_database(
    database: SQLiteDatabase, *, migrate: bool
) -> dict[str, Any]:
    if not database.path.is_file() and not migrate:
        raise FileNotFoundError(f"SORA database does not exist: {database.path}")
    if migrate:
        await database.initialize()

    def inspect(connection: sqlite3.Connection) -> dict[str, Any]:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        if quick_check != "ok" or foreign_key_rows:
            raise ValueError(
                f"state integrity failed: quick_check={quick_check}, "
                f"foreign_key_errors={len(foreign_key_rows)}"
            )
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in ("owners", "projects", "conversations", "messages", "tasks", "artifacts")
            if table in tables
        }
        return {"quick_check": quick_check, "foreign_key_errors": 0, "counts": counts}

    result = await database.read(inspect)
    result["schema_version"] = await database.schema_version()
    result["database"] = str(database.path)
    return result


async def verify_state(root: Path, *, migrate: bool = False) -> dict[str, Any]:
    state_root = root.resolve(strict=migrate is False)
    return await _require_healthy_database(
        SQLiteDatabase(state_root / "data" / "sora.db"), migrate=migrate
    )


def write_state_marker(state_root: Path, install_root: Path) -> None:
    marker = {
        "schema_version": 1,
        "state_root": str(state_root.resolve()),
        "install_root": str(install_root.resolve()),
        "personal_data": True,
    }
    (state_root / ".sora-state.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
