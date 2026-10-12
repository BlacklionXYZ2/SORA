"""The whole turn behind a memory (MEMORY_MANAGER_2026-10-08 §3.1, §6).

When SORA remembers a moment with the ``remember`` tool, Core keeps everything the turn had in
``<state>/memory/entries/<memory_id>/``:

- ``entry.json``: her title and description, the owner's exact words, her reply, what was read,
  the time, app and models, and later the memory manager's verdict on each part;
- ``image-<n>.<ext>``: the images the brain saw (the desktop overview, a closer window, images
  the owner attached), as the brain received them;
- ``voice.wav``: the owner's recording, when the turn was spoken and the brain heard audio.

The folder is written atomically and only ever read by Core (never sent to a prompt, a status
file or another device). Forgetting the memory deletes the folder.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import os
import shutil
import uuid
import wave
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from sora.contracts.base import StrictModel

ImageSource = Literal["owner", "screen"]
MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8_000_000
MAX_AUDIO_BYTES = 2_000_000
MAX_READ_CHARS = 8_000
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class EntryMedia(StrictModel):
    file: str
    mime: str
    bytes: int = Field(ge=0)
    sha256: str
    source: Literal["owner", "screen", "voice"]
    seconds: float | None = None  # audio only


class PartVerdict(StrictModel):
    """The memory manager's decision about one part (kept with the memory or not)."""

    kept: bool
    relevance: float | None = None
    policy: str = "fixed-threshold"


class TurnEntry(StrictModel):
    version: Literal[1] = 1
    memory_id: str
    created_at: datetime
    title: str
    description: str
    owner_text: str
    reply: str = ""
    read_observations: str = ""
    media: list[EntryMedia] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    status: Literal["pending", "processed"] = "pending"
    parts: dict[str, PartVerdict] = Field(default_factory=dict)


def _decode_image(data_url: str) -> tuple[bytes, str] | None:
    head, _, payload = data_url.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64")
    if not head.endswith(";base64") or mime not in _EXTENSIONS:
        return None
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    return (data, mime) if 0 < len(data) <= MAX_IMAGE_BYTES else None


def _wav_seconds(data: bytes) -> float | None:
    try:
        with wave.open(io.BytesIO(data)) as clip:
            frames, rate = int(clip.getnframes()), int(clip.getframerate())
            return round(frames / rate, 2)
    except (wave.Error, EOFError, ZeroDivisionError):
        return None


def write_entry(
    root: Path, *, memory_id: str, created_at: datetime, title: str, description: str,
    owner_text: str, reply: str = "", read_observations: str = "",
    images: Sequence[tuple[str, ImageSource]] = (), audio_wav_base64: str | None = None,
    context: Mapping[str, str] | None = None,
) -> TurnEntry:
    """Write the entry folder in one step (a temporary folder, then a rename)."""
    final = root / memory_id
    staging = root / f".{memory_id}.{uuid.uuid4().hex}.partial"
    staging.mkdir(parents=True)
    media: list[EntryMedia] = []
    try:
        for data_url, source in images[:MAX_IMAGES]:
            decoded = _decode_image(data_url)
            if decoded is None:
                continue
            data, mime = decoded
            name = f"image-{len(media) + 1}.{_EXTENSIONS[mime]}"
            (staging / name).write_bytes(data)
            media.append(EntryMedia(file=name, mime=mime, bytes=len(data),
                                    sha256=hashlib.sha256(data).hexdigest(), source=source))
        if audio_wav_base64:
            try:
                data = base64.b64decode(audio_wav_base64, validate=True)
            except (binascii.Error, ValueError):
                data = b""
            if 44 <= len(data) <= MAX_AUDIO_BYTES and data[:4] == b"RIFF":
                (staging / "voice.wav").write_bytes(data)
                media.append(EntryMedia(file="voice.wav", mime="audio/wav", bytes=len(data),
                                        sha256=hashlib.sha256(data).hexdigest(),
                                        source="voice", seconds=_wav_seconds(data)))
        entry = TurnEntry(
            memory_id=memory_id, created_at=created_at, title=title, description=description,
            owner_text=owner_text, reply=reply, read_observations=read_observations[
                :MAX_READ_CHARS], media=media, context=dict(context or {}))
        (staging / "entry.json").write_text(entry.model_dump_json(indent=2), encoding="utf-8")
        os.replace(staging, final)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return entry


def read_entry(root: Path, memory_id: str) -> TurnEntry | None:
    try:
        return TurnEntry.model_validate_json((root / memory_id / "entry.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None


def save_entry(root: Path, entry: TurnEntry) -> None:
    """Update entry.json (the manager's verdicts) atomically."""
    target = root / entry.memory_id / "entry.json"
    partial = target.with_suffix(".partial")
    partial.write_text(entry.model_dump_json(indent=2), encoding="utf-8")
    os.replace(partial, target)


def media_bytes(root: Path, entry: TurnEntry, media: EntryMedia) -> bytes:
    path = (root / entry.memory_id / media.file).resolve()
    if path.parent != (root / entry.memory_id).resolve():
        raise ValueError("media outside its entry")
    return path.read_bytes()


def forget_entry(root: Path, memory_id: str) -> bool:
    """The owner forgot the memory: delete its turn data, images and recording."""
    folder = root / memory_id
    if not folder.is_dir() or folder.resolve().parent != root.resolve():
        return False
    shutil.rmtree(folder)
    return True
