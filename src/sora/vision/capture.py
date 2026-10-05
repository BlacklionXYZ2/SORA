"""Capacity-, byte-, scope-, and TTL-bounded volatile PNG capture storage."""

from __future__ import annotations

import base64
import binascii
import hashlib
import struct
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from sora.contracts.capture import DesktopCaptureFrame


def validate_png_dimensions(data: bytes, width: int, height: int) -> None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ValueError("capture frame is not a PNG")
    if struct.unpack(">II", data[16:24]) != (width, height):
        raise ValueError("capture PNG dimensions do not match its scoped region")


def decode_png_frame(frame: DesktopCaptureFrame) -> bytes:
    try:
        data = base64.b64decode(frame.image_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("capture frame is not valid base64") from exc
    if len(data) != frame.byte_length:
        raise ValueError("capture frame byte length mismatch")
    if hashlib.sha256(data).hexdigest() != frame.sha256:
        raise ValueError("capture frame digest mismatch")
    validate_png_dimensions(data, frame.region.width, frame.region.height)
    return data


@dataclass(frozen=True, slots=True)
class _StoredCapture:
    frame: DesktopCaptureFrame
    owner_id: str
    device_id: str
    project_id: str | None
    byte_length: int


class DesktopCaptureStore:
    """Frames exist only in process memory and disappear on expiry, eviction, or shutdown."""

    def __init__(self, *, capacity: int = 8, max_total_bytes: int = 33_554_432) -> None:
        if not 1 <= capacity <= 64:
            raise ValueError("capture capacity must be between 1 and 64")
        if not 1 <= max_total_bytes <= 134_217_728:
            raise ValueError("capture byte budget must be between 1 and 134217728")
        self.capacity = capacity
        self.max_total_bytes = max_total_bytes
        self._captures: OrderedDict[tuple[str, str, str | None, str], _StoredCapture] = (
            OrderedDict()
        )
        self._total_bytes = 0

    @property
    def count(self) -> int:
        return len(self._captures)

    @property
    def total_bytes(self) -> int:
        return self._total_bytes

    def put(
        self,
        frame: DesktopCaptureFrame,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> None:
        evaluated_at = now or datetime.now(UTC)
        self.prune(evaluated_at)
        data = decode_png_frame(frame)
        if frame.expires_at <= evaluated_at:
            raise ValueError("capture frame expired before storage")
        if len(data) > self.max_total_bytes:
            raise ValueError("capture frame exceeds the volatile byte budget")
        key = (owner_id, device_id, project_id, frame.capture_id)
        if key in self._captures:
            raise ValueError("capture ID was already used in this scope")
        stored = _StoredCapture(
            frame=frame,
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            byte_length=len(data),
        )
        self._captures[key] = stored
        self._total_bytes += stored.byte_length
        while len(self._captures) > self.capacity or self._total_bytes > self.max_total_bytes:
            _, evicted = self._captures.popitem(last=False)
            self._total_bytes -= evicted.byte_length

    def get(
        self,
        capture_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> DesktopCaptureFrame | None:
        self.prune(now or datetime.now(UTC))
        key = (owner_id, device_id, project_id, capture_id)
        stored = self._captures.get(key)
        if stored is None:
            return None
        self._captures.move_to_end(key)
        return stored.frame

    def remove(
        self,
        capture_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
    ) -> bool:
        key = (owner_id, device_id, project_id, capture_id)
        stored = self._captures.pop(key, None)
        if stored is None:
            return False
        self._total_bytes -= stored.byte_length
        return True

    def prune(self, now: datetime) -> int:
        removed = 0
        for key, stored in tuple(self._captures.items()):
            if stored.frame.expires_at > now:
                continue
            del self._captures[key]
            self._total_bytes -= stored.byte_length
            removed += 1
        return removed

    def clear(self) -> None:
        self._captures.clear()
        self._total_bytes = 0
