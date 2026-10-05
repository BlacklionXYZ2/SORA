"""Hash-manifest creation and verification for portable SORA release bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

RELEASE_MANIFEST = "release-manifest.json"
RELEASE_SCHEMA_VERSION = 1
_RELEASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


class ReleaseVerificationError(ValueError):
    """Raised when a bundle is malformed, unsafe, incomplete, or modified."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or ".." in path.parts
        or ":" in value
        or "\\" in value
    ):
        raise ReleaseVerificationError(f"unsafe release path: {value}")
    return path


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.stat(follow_symlinks=False), "st_file_attributes", 0)
    reparse_flag = getattr(os.stat_result, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return path.is_symlink() or bool(attributes & reparse_flag)


def _release_files(bundle_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(bundle_root.rglob("*")):
        if _is_reparse_point(path):
            raise ReleaseVerificationError(
                f"release cannot contain links or reparse points: {path}"
            )
        if path.is_file() and path.name != RELEASE_MANIFEST:
            files.append(path)
    return files


def validate_release_id(release_id: str) -> str:
    value = release_id.strip()
    if not _RELEASE_ID.fullmatch(value):
        raise ReleaseVerificationError("release_id must be 1-80 safe filename characters")
    return value


def build_release_manifest(
    bundle_root: Path,
    *,
    release_id: str,
    app_version: str,
    metadata: dict[str, Any],
    created_at: datetime | None = None,
) -> Path:
    """Create a complete manifest after the bundle contents have been staged."""

    root = bundle_root.resolve(strict=True)
    clean_release_id = validate_release_id(release_id)
    required = {
        "payload/core/python/python.exe",
        "payload/resources/identity/persona.md",
        "install.ps1",
        "update.ps1",
        "uninstall.ps1",
    }
    entries: list[dict[str, Any]] = []
    for path in _release_files(root):
        relative = path.relative_to(root).as_posix()
        _safe_relative(relative)
        entries.append(
            {
                "path": relative,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    present = {str(entry["path"]) for entry in entries}
    missing = sorted(required - present)
    if missing:
        raise ReleaseVerificationError(f"release is missing required files: {missing}")
    manifest = {
        "schema_version": RELEASE_SCHEMA_VERSION,
        "release_id": clean_release_id,
        "app_version": app_version,
        "created_at": (created_at or datetime.now(UTC)).isoformat(),
        "platform": "windows-x64",
        "files": entries,
        "metadata": metadata,
    }
    destination = root / RELEASE_MANIFEST
    destination.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return destination


def verify_release_manifest(bundle_root: Path) -> dict[str, Any]:
    """Verify paths, exact file set, byte counts, and hashes before installation."""

    root = bundle_root.resolve(strict=True)
    manifest_path = root / RELEASE_MANIFEST
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseVerificationError("release manifest is missing or invalid") from exc
    if manifest.get("schema_version") != RELEASE_SCHEMA_VERSION:
        raise ReleaseVerificationError("unsupported release manifest schema")
    validate_release_id(str(manifest.get("release_id", "")))
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ReleaseVerificationError("release manifest has no files")
    expected: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ReleaseVerificationError("release manifest contains an invalid file entry")
        relative = _safe_relative(entry["path"])
        name = relative.as_posix()
        if name in expected:
            raise ReleaseVerificationError(f"duplicate release path: {name}")
        expected[name] = entry
        source = root.joinpath(*relative.parts)
        if not source.is_file() or _is_reparse_point(source):
            raise ReleaseVerificationError(f"release file is missing or unsafe: {name}")
        if source.stat().st_size != entry.get("bytes"):
            raise ReleaseVerificationError(f"release size mismatch: {name}")
        if _sha256(source) != entry.get("sha256"):
            raise ReleaseVerificationError(f"release hash mismatch: {name}")
    actual = {path.relative_to(root).as_posix() for path in _release_files(root)}
    if actual != set(expected):
        unexpected = sorted(actual - set(expected))
        missing = sorted(set(expected) - actual)
        raise ReleaseVerificationError(
            f"release file set mismatch; unexpected={unexpected}, missing={missing}"
        )
    return cast(dict[str, Any], manifest)
