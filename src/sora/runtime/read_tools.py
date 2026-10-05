"""Transient native/file read tools; no shell, writes, grant creation or project allowlist."""

from __future__ import annotations

import asyncio
import os
import stat
import threading
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sora.contracts.companion_read import (
    CompanionReadCall,
    CompanionReadResult,
    FinishRead,
    InspectWindow,
    ListFiles,
    ListWindows,
    ReadFile,
    SearchFiles,
)
from sora.contracts.desktop import DesktopNode, DesktopObservation, DesktopObservationRequest
from sora.desktop.foreground import ForegroundIdentity
from sora.runtime.companion_targets import ControlReferences
from sora.runtime.local_files import LocalFileViewError, read_local_file
from sora.security.operations import OperationAuthorizationError

_NON_TEXT = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".pptx",
    ".exe",
    ".dll",
    ".lnk",
    ".zip",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".mp4",
    ".mp3",
}


def desktop_directories() -> list[str]:
    """Resolve actual owner/Public Desktop folders; never read their file bodies implicitly."""
    paths = [Path.home() / "Desktop"]
    if os.name == "nt":
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                paths[0] = Path(os.path.expandvars(str(winreg.QueryValueEx(key, "Desktop")[0])))
        except OSError:
            pass
        paths.append(Path(os.environ.get("PUBLIC", str(Path.home().parent / "Public"))) / "Desktop")
    return list(dict.fromkeys(str(path) for path in paths if path.is_dir()))


def local_path(raw: str, *, directory: bool = False) -> Path:
    if raw.startswith(("\\\\", "//")) or not Path(raw).is_absolute():
        raise LocalFileViewError("Use an absolute local path, not a network location")
    if os.name == "nt":
        import ctypes

        if ctypes.windll.kernel32.GetDriveTypeW(str(Path(raw).anchor)) == 4:
            raise LocalFileViewError("Mapped network drives are not supported")
    path = Path(raw).resolve(strict=True)
    if str(path).startswith(("\\\\", "//")):
        raise LocalFileViewError("Network locations are not supported")
    info = path.stat()
    if getattr(info, "st_file_attributes", 0) & (0x1000 | 0x40000 | 0x400000):
        raise LocalFileViewError("Cloud-only/offline files are not downloaded by the reader")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise LocalFileViewError("Expected a directory" if directory else "Expected a regular file")
    return path


def _entries(root: Path, recursive: bool, depth: int = 0) -> Iterator[Path | None]:
    with os.scandir(root) as entries:
        for entry in entries:
            try:
                info = entry.stat(follow_symlinks=False)
                if entry.is_symlink() or (
                    stat.S_ISDIR(info.st_mode) and getattr(info, "st_file_attributes", 0) & 0x400
                ):
                    yield None
                    continue  # No recursive junction/reparse loops or implicit cloud hydration.
                path = Path(entry.path)
                yield path
                if recursive and stat.S_ISDIR(info.st_mode) and depth < 8:
                    try:
                        yield from _entries(path, True, depth + 1)
                    except OSError:
                        yield None
                elif recursive and stat.S_ISDIR(info.st_mode):
                    yield None
            except OSError:
                yield None


class CompanionReadTools:
    def __init__(
        self,
        *,
        check: Callable[[str], None],
        observe: Callable[[DesktopObservationRequest], Awaitable[DesktopObservation]],
        recent_application: Callable[[], ForegroundIdentity | None] = lambda: None,
        presentation_targets: ControlReferences | None = None,
    ):
        self.check = check
        self.observe = observe
        self.recent_application = recent_application
        self.presentation_targets = presentation_targets or ControlReferences()
        self.windows: dict[str, tuple[DesktopNode, float]] = {}
        self.files: dict[str, tuple[Path, int, int]] = {}
        self.cursors: dict[str, tuple[str, str, str, int, int]] = {}
        self._counter = 0
        self.cancelled = threading.Event()

    def _reference(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}{self._counter}"

    async def execute(self, call: CompanionReadCall) -> CompanionReadResult:
        operation = call.root
        source = (
            "windows.win32"
            if isinstance(operation, ListWindows)
            else "windows.uia"
            if isinstance(operation, InspectWindow)
            else "filesystem"
        )
        result = CompanionReadResult(
            call_id=f"read-{uuid.uuid4().hex}",
            status="ok",
            source=source,
            observed_at=datetime.now(UTC),
        )
        if isinstance(operation, FinishRead):
            return result.model_copy(update={"source": "core"})
        effect = (
            "desktop_observe"
            if isinstance(operation, (ListWindows, InspectWindow))
            else "file_read"
        )
        try:
            self.check(effect)
            if isinstance(operation, ListWindows):
                observation = await self.observe(DesktopObservationRequest(operation="inventory"))
                data = []
                recent = self.recent_application()
                recent_ref = None
                for node in observation.nodes:
                    ref = self._reference("w")
                    self.windows[ref] = (node, time.monotonic())
                    if recent and (
                        node.process_id,
                        node.window_handle,
                        node.process_started_at,
                    ) == (
                        recent.process_id,
                        recent.window_handle,
                        recent.process_started_at,
                    ):
                        recent_ref = ref
                    data.append(
                        {
                            "target": ref,
                            "title": node.name,
                            "foreground": node.focused,
                            "minimized": node.offscreen,
                        }
                    )
                result = self._observation_result(
                    result,
                    observation,
                    {
                        "windows": data,
                        "count": len(data),
                        "recent_application_target": recent_ref,
                        "recent_application_at": (
                            recent.observed_at.isoformat() if recent and recent_ref else None
                        ),
                        "recent_application_note": (
                            "Last non-SORA foreground, revalidated now; use for 'my window' "
                            "when chat has focus. This is not current selection/content."
                            if recent_ref
                            else "No recent non-SORA target could be revalidated"
                        ),
                        "scope": "Visible top-level windows, including helper and untitled windows",
                    },
                )
            elif isinstance(operation, InspectWindow):
                stored = self.windows.get(operation.target)
                if stored is None or time.monotonic() - stored[1] > 60:
                    return result.model_copy(
                        update={
                            "status": "stale",
                            "data": {"reason": "List windows again to obtain a current reference"},
                        }
                    )
                node = stored[0]
                view: Literal["tree", "text", "selection"] = (
                    "selection"
                    if operation.view == "selection"
                    else "text"
                    if operation.view == "text"
                    else "tree"
                )
                observation = await self.observe(
                    DesktopObservationRequest(
                        operation=view,
                        process_id=node.process_id,
                        window_handle=node.window_handle,
                        max_nodes=64,
                        max_depth=2 if operation.view == "summary" else 8,
                    )
                )
                if observation.status != "ok":
                    return self._observation_result(result, observation, {})
                if node.process_started_at is None or (
                    observation.process_started_at != node.process_started_at
                ):
                    return result.model_copy(
                        update={
                            "status": "stale",
                            "data": {
                                "reason": "Window process identity changed or cannot be verified"
                            },
                        }
                    )
                result = self._observation_result(
                    result,
                    observation,
                    {
                        "window": node.name,
                        "view": operation.view,
                        **(
                            {
                                "selected_text": "\n".join(
                                    item.selected_text
                                    for item in observation.nodes
                                    if item.selected_text
                                ),
                                "selection_supported": any(
                                    item.selection_available for item in observation.nodes
                                ),
                            }
                            if operation.view in {"selection", "text"}
                            else {}
                        ),
                        **(
                            {
                                "text": "\n".join(
                                    item.text for item in observation.nodes if item.text
                                ),
                                "text_supported": any(
                                    item.text_available for item in observation.nodes
                                ),
                            }
                            if operation.view == "text"
                            else {}
                        ),
                        "nodes": [
                            self.presentation_targets.describe(item, node, observation)
                            for item in observation.nodes
                        ],
                        "note": "UIA text only; empty output may mean unsupported UIA",
                    },
                )
            elif isinstance(operation, (ListFiles, SearchFiles)):
                result = await self._list(result, operation)
            elif isinstance(operation, ReadFile):
                path = operation.path
                if operation.target is not None:
                    found = self.files.get(operation.target)
                    if found is None:
                        return result.model_copy(update={"status": "stale"})
                    info = found[0].stat()
                    if (info.st_size, info.st_mtime_ns) != found[1:]:
                        return result.model_copy(
                            update={
                                "status": "stale",
                                "data": {"reason": "The listed file changed; list it again"},
                            }
                        )
                    path = str(found[0])
                assert path is not None
                result = await asyncio.to_thread(self._read, result, path, operation.offset)
            self.check(
                effect
            )  # Do not deliver private data after policy changed during native I/O.
            return result
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        except OperationAuthorizationError as exc:
            self.windows.clear()
            self.files.clear()
            self.cursors.clear()
            self.presentation_targets.clear()
            return result.model_copy(update={"status": "disabled", "data": {"reason": str(exc)}})
        except FileNotFoundError:
            return result.model_copy(update={"status": "not_found"})
        except (OSError, LocalFileViewError, ValueError) as exc:
            return result.model_copy(
                update={"status": "unsupported", "data": {"reason": str(exc)[:300]}}
            )

    @staticmethod
    def _observation_result(
        result: CompanionReadResult, observation: DesktopObservation, data: dict[str, object]
    ) -> CompanionReadResult:
        if observation.status != "ok":
            return result.model_copy(
                update={
                    "status": "timeout" if observation.status == "timeout" else "unsupported",
                    "data": {"reason": observation.status},
                }
            )
        truncated = observation.truncated or any(node.text_truncated for node in observation.nodes)
        return result.model_copy(
            update={
                "status": "partial" if truncated else "ok",
                "data": data,
                "truncated": truncated,
            }
        )

    async def _list(
        self, result: CompanionReadResult, call: ListFiles | SearchFiles
    ) -> CompanionReadResult:
        root = local_path(call.path, directory=True)
        query = call.query if isinstance(call, SearchFiles) else ""
        mode = call.mode if isinstance(call, SearchFiles) else "list"
        modified = root.stat().st_mtime_ns
        offset = 0
        if call.cursor:
            saved = self.cursors.get(call.cursor)
            if saved is None or saved[:3] != (str(root), query, mode) or saved[4] != modified:
                return result.model_copy(
                    update={
                        "status": "stale",
                        "data": {
                            "reason": "Cursor does not match this search or directory changed"
                        },
                    }
                )
            offset = saved[3]
        rows, scanned, more, skipped = await asyncio.to_thread(
            self._scan, root, query, mode, offset
        )
        self.check("file_read")
        entries = []
        for path in rows:
            try:
                info = path.stat()
                directory = path.is_dir()
                ref = self._reference("d" if directory else "f")
                if not directory:
                    self.files[ref] = (path, info.st_size, info.st_mtime_ns)
                entries.append(
                    {
                        "target": ref,
                        "path": str(path),
                        "kind": "directory" if directory else "file",
                        "bytes": info.st_size,
                    }
                )
            except OSError:
                skipped += 1
                continue
        cursor = None
        if more and scanned < 10_000:
            cursor = "c-" + uuid.uuid4().hex
            self.cursors[cursor] = (str(root), query, mode, scanned, modified)
        return result.model_copy(
            update={
                "status": "partial" if more or skipped else "ok",
                "data": {
                    "path": str(root),
                    "entries": entries,
                    "scanned": scanned,
                    "skipped": skipped,
                    "limits": "Best-effort: depth 8, 10000 entries; text search reads first 64 KiB",
                },
                "truncated": more or bool(skipped),
                "continuation": cursor,
            }
        )

    def _scan(
        self,
        root: Path,
        query: str,
        mode: str,
        offset: int,
    ) -> tuple[list[Path], int, bool, int]:
        rows: list[Path] = []
        deadline = time.monotonic() + 0.25
        scanned = 0
        skipped = 0
        for index, path in enumerate(_entries(root, mode != "list")):
            if self.cancelled.is_set():
                return rows, scanned, True, skipped
            self.check("file_read")
            scanned = index + 1
            if index < offset:
                continue
            if scanned > 10_000:
                return rows, 10_000, True, skipped
            if path is None:
                skipped += 1
                if time.monotonic() >= deadline or scanned - offset >= 500:
                    return rows, scanned, True, skipped
                continue
            matches = mode == "list" or (
                mode == "name" and query.casefold() in path.name.casefold()
            )
            if mode == "text" and path.is_file():
                try:
                    if path.suffix.lower() in _NON_TEXT:
                        skipped += 1
                        if time.monotonic() >= deadline or scanned - offset >= 500:
                            return rows, scanned, True, skipped
                        continue
                    view = read_local_file(str(local_path(str(path))))
                    matches = (
                        view.image_data_url is None
                        and not view.text.startswith("Binary file:")
                        and query.casefold() in view.text.casefold()
                    )
                except (LocalFileViewError, OSError):
                    skipped += 1
            if matches:
                rows.append(path)
            if len(rows) >= 40 or time.monotonic() >= deadline or scanned - offset >= 500:
                return rows, scanned, True, skipped
        return rows, scanned, False, skipped

    def _read(self, result: CompanionReadResult, raw: str, offset: int) -> CompanionReadResult:
        path = local_path(raw)
        if path.suffix.lower() in _NON_TEXT:
            return result.model_copy(
                update={
                    "status": "unsupported",
                    "data": {
                        "path": str(path),
                        "reason": "No document-text adapter for this file format",
                    },
                }
            )
        before = path.stat()
        if self.cancelled.is_set():
            raise OperationAuthorizationError("Read cancelled")
        self.check("file_read")
        view = read_local_file(str(path))
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ):
            return result.model_copy(
                update={
                    "status": "stale",
                    "data": {
                        "reason": "File changed while being read; retry",
                    },
                }
            )
        if view.image_data_url is not None or view.text.startswith("Binary file:"):
            return result.model_copy(
                update={
                    "status": "unsupported",
                    "data": {
                        "path": str(path),
                        "reason": "This read tool returns text, not pixels or binary bytes",
                    },
                }
            )
        if offset > len(view.text):
            return result.model_copy(
                update={
                    "status": "unsupported",
                    "data": {"reason": "Offset is beyond the bounded decoded file view"},
                }
            )
        text = view.text[offset : offset + 8192]
        more = offset + len(text) < len(view.text)
        truncated = more or "view truncated" in view.text.lower()
        return result.model_copy(
            update={
                "status": "partial" if truncated else "ok",
                "data": {
                    "path": str(path),
                    "text": text,
                    "offset": offset,
                    "next_offset": offset + len(text) if more else None,
                    "limit": "Decoded view limited to first 64 KiB; truncation marker is retained",
                },
                "truncated": truncated,
            }
        )
