"""Bounded, read-only views of owner-local files for a dialogue turn.

Paths are intentionally not restricted to configured content roots. The caller must
already be the local owner; remote paired sessions must never reach this reader.
Only a small transient view is sent to a local dialogue model, not persisted.
"""

from __future__ import annotations

import base64
import mimetypes
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

_TEXT_BYTES = 65_536
_IMAGE_BYTES = 16_777_216
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


class LocalFileViewError(ValueError):
    """A selected path cannot be represented as a safe local dialogue view."""


@dataclass(frozen=True, slots=True)
class LocalFileView:
    path: Path
    size: int
    text: str
    image_data_url: str | None = None


def _docx_text(path: Path) -> str | None:
    try:
        with zipfile.ZipFile(path) as archive:
            entry = archive.getinfo("word/document.xml")
            if entry.file_size > 1_048_576:
                return None
            with archive.open(entry) as stream:
                xml = ElementTree.fromstring(stream.read(_TEXT_BYTES * 16 + 1))
    except (KeyError, OSError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
        return None
    return " ".join(node.text or "" for node in xml.iter() if node.tag.endswith("}t"))


def read_local_file(path_text: str) -> LocalFileView:
    """Read any regular local file accessible to this process; bound model payloads."""
    raw = path_text.strip().strip('"')
    if not raw or len(raw) > 4096 or raw.startswith(("\\\\", "//")):
        raise LocalFileViewError("Choose an existing local file path.")
    try:
        path = Path(raw).expanduser().resolve(strict=True)
        if str(path).startswith(("\\\\", "//")):
            raise LocalFileViewError("Choose a local file, not a network path.")
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            raise LocalFileViewError("The selected path is not a regular file.")
        if path.suffix.lower() in _IMAGE_SUFFIXES and info.st_size <= _IMAGE_BYTES:
            data = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return LocalFileView(
                path=path,
                size=info.st_size,
                text=f"Image file: {path.name} ({info.st_size} bytes).",
                image_data_url=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
            )
        if path.suffix.lower() == ".docx":
            document = _docx_text(path)
            if document is not None:
                clipped = document[:_TEXT_BYTES]
                suffix = "\n[Document view truncated]" if len(document) > len(clipped) else ""
                return LocalFileView(
                    path=path,
                    size=info.st_size,
                    text=clipped + suffix,
                )
        with path.open("rb") as stream:
            data = stream.read(_TEXT_BYTES + 1)
    except (OSError, PermissionError) as exc:
        raise LocalFileViewError("The selected local file could not be read.") from exc
    if len(data) > _TEXT_BYTES:
        data = data[:_TEXT_BYTES]
    if b"\x00" in data:
        rendered = data[:4096].hex(" ")
        text = f"Binary file: {path.name} ({info.st_size} bytes). First bytes (hex): {rendered}"
    else:
        text = data.decode("utf-8", errors="replace")
    if info.st_size > len(data):
        text += "\n[File view truncated; more bytes remain]"
    return LocalFileView(path=path, size=info.st_size, text=text)
