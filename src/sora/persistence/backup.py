"""Consistent database/artifact backup and clean-directory restore."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from .database import SQLiteDatabase


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def create_backup(
    database: SQLiteDatabase,
    *,
    artifacts_root: Path,
    destination: Path,
    artifacts_archive_prefix: str = "artifacts",
) -> Path:
    return await asyncio.to_thread(
        _create_backup_sync,
        database.path,
        artifacts_root,
        destination,
        artifacts_archive_prefix,
    )


def _safe_archive_prefix(value: str) -> PurePosixPath:
    prefix = PurePosixPath(value)
    if not value or prefix.is_absolute() or ".." in prefix.parts or ":" in value:
        raise ValueError(f"unsafe artifact archive prefix: {value}")
    return prefix


def _create_backup_sync(
    database_path: Path,
    artifacts_root: Path,
    destination: Path,
    artifacts_archive_prefix: str,
) -> Path:
    archive_prefix = _safe_archive_prefix(artifacts_archive_prefix)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"backup destination is not empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    database_destination = destination / "data" / "sora.db"
    database_destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(database_path) as source_db,
        sqlite3.connect(database_destination) as target_db,
    ):
        source_db.backup(target_db)

    if artifacts_root.exists():
        for source_path in artifacts_root.rglob("*"):
            relative = source_path.relative_to(artifacts_root)
            if "secrets" in relative.parts:
                continue
            if source_path.is_file():
                target = destination.joinpath(*archive_prefix.parts, *relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target)

    files = []
    for path in sorted(item for item in destination.rglob("*") if item.is_file()):
        relative_name = path.relative_to(destination).as_posix()
        files.append({"path": relative_name, "sha256": _sha256(path), "bytes": path.stat().st_size})
    manifest = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "files": files,
        "excluded": [f"{archive_prefix.as_posix()}/**/secrets/**"],
    }
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest_path


async def restore_backup(*, backup: Path, destination: Path) -> None:
    await asyncio.to_thread(_restore_backup_sync, backup, destination)


def _restore_backup_sync(backup: Path, destination: Path) -> None:
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f"restore destination is not empty: {destination}")

    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise ValueError("backup manifest has no file list")
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("backup manifest contains an invalid file entry")
        relative = PurePosixPath(entry["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe backup path: {entry['path']}")
        source = backup.joinpath(*relative.parts)
        if _sha256(source) != entry.get("sha256"):
            raise ValueError(f"backup hash mismatch: {entry['path']}")

    destination.mkdir(parents=True, exist_ok=True)
    for entry in entries:
        relative = PurePosixPath(entry["path"])
        source = backup.joinpath(*relative.parts)
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
