"""Bounded serialized SQLite access with explicit migrations."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .migrations import CURRENT_SCHEMA_VERSION, MIGRATIONS


class SQLiteDatabase:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._write_lock = asyncio.Lock()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    async def initialize(self, *, target_version: int = CURRENT_SCHEMA_VERSION) -> None:
        if target_version < 1 or target_version > CURRENT_SCHEMA_VERSION:
            raise ValueError(f"unsupported target schema version {target_version}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self._write_lock:
            await asyncio.to_thread(self._initialize_sync, target_version)

    def _initialize_sync(self, target_version: int) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            existing = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
            ).fetchone()
            current = (
                int(
                    connection.execute(
                        "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                    ).fetchone()[0]
                )
                if existing
                else 0
            )
            for migration in MIGRATIONS:
                if current < migration.version <= target_version:
                    try:
                        connection.execute("BEGIN IMMEDIATE")
                        for statement in migration.statements:
                            connection.execute(statement)
                        connection.execute(
                            "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                            (migration.version, datetime.now(UTC).isoformat()),
                        )
                        connection.commit()
                    except Exception:
                        connection.rollback()
                        raise

    async def schema_version(self) -> int:
        def read(connection: sqlite3.Connection) -> int:
            row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
            return int(row[0])

        return await self.read(read)

    async def read[ResultT](self, operation: Callable[[sqlite3.Connection], ResultT]) -> ResultT:
        def run() -> ResultT:
            with self._connect() as connection:
                return operation(connection)

        return await asyncio.to_thread(run)

    async def write[ResultT](self, operation: Callable[[sqlite3.Connection], ResultT]) -> ResultT:
        async with self._write_lock:

            def run() -> ResultT:
                with self._connect() as connection:
                    try:
                        connection.execute("BEGIN IMMEDIATE")
                        result = operation(connection)
                        connection.commit()
                        return result
                    except Exception:
                        connection.rollback()
                        raise

            return await asyncio.to_thread(run)
