"""Validate exact saved-file editor selections without guessing metadata."""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from sora.contracts.editor import EditorContextRequest, EditorContextSnapshot, EditorPosition


class EditorContextError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left)) == os.path.normcase(str(right))


def _canonical_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _position_offset(lines: list[str], position: EditorPosition) -> int:
    if position.line > len(lines):
        raise EditorContextError("invalid_selection", "selection line is outside the document")
    line = lines[position.line - 1]
    if position.column > len(line) + 1:
        raise EditorContextError("invalid_selection", "selection column is outside the line")
    return sum(len(item) + 1 for item in lines[: position.line - 1]) + position.column - 1


def resolve_editor_context(
    request: EditorContextRequest,
    *,
    allowed_roots: tuple[Path, ...],
    owner_id: str,
    device_id: str,
    project_id: str | None,
    now: datetime,
    file_bytes: bytes,
    max_file_bytes: int,
) -> EditorContextSnapshot:
    """Bind app-reported metadata to a configured root and exact saved file bytes."""
    if request.captured_at > now + timedelta(seconds=5):
        raise EditorContextError("future_capture", "editor capture timestamp is in the future")
    if now - request.captured_at > timedelta(seconds=60):
        raise EditorContextError("stale_capture", "editor context is older than 60 seconds")

    requested_root = Path(request.repository_root)
    if not requested_root.is_absolute():
        raise EditorContextError("repository_not_allowed", "repository root must be absolute")
    canonical_root = requested_root.resolve(strict=False)
    configured_root = next(
        (root for root in allowed_roots if _same_path(root.resolve(strict=False), canonical_root)),
        None,
    )
    if configured_root is None:
        raise EditorContextError("repository_not_allowed", "repository root is not configured")
    canonical_root = configured_root.resolve(strict=True)

    relative_path = Path(request.relative_file_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise EditorContextError("file_outside_repository", "file path must stay in repository")
    try:
        file_path = (canonical_root / relative_path).resolve(strict=True)
        normalized_relative = file_path.relative_to(canonical_root)
    except (OSError, ValueError) as exc:
        raise EditorContextError(
            "file_outside_repository", "file is unavailable or outside the configured repository"
        ) from exc
    if not file_path.is_file():
        raise EditorContextError("file_unavailable", "editor file is not a regular file")
    if len(file_bytes) > max_file_bytes:
        raise EditorContextError("file_too_large", "editor file exceeds the configured read bound")

    actual_document_hash = hashlib.sha256(file_bytes).hexdigest()
    if actual_document_hash != request.document_sha256:
        raise EditorContextError(
            "document_changed", "saved file digest does not match the editor metadata"
        )
    try:
        document = _canonical_text(file_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise EditorContextError("unsupported_encoding", "editor file must be UTF-8") from exc

    lines = document.split("\n")
    start = _position_offset(lines, request.selection.start)
    end = _position_offset(lines, request.selection.end)
    actual_selection = document[start:end]
    reported_selection = _canonical_text(request.selected_text)
    if actual_selection != reported_selection:
        raise EditorContextError(
            "selection_mismatch", "reported selection does not match the saved file range"
        )
    selection_hash = hashlib.sha256(actual_selection.encode("utf-8")).hexdigest()
    verified_at = max(now, request.captured_at)
    return EditorContextSnapshot(
        context_id=f"editor-context-{uuid.uuid4()}",
        owner_id=owner_id,
        device_id=device_id,
        project_id=project_id,
        editor_name=request.editor_name,
        repository_root=str(canonical_root),
        relative_file_path=normalized_relative.as_posix(),
        document_sha256=actual_document_hash,
        selection=request.selection,
        selected_text=actual_selection,
        selection_sha256=selection_hash,
        desktop_target_id=request.desktop_target_id,
        captured_at=request.captured_at,
        verified_at=verified_at,
    )
