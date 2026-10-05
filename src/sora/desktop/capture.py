"""Killable one-request Windows capture helper transport for P13.2."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from sora.contracts.base import StrictModel, require_aware
from sora.contracts.capture import (
    DesktopCaptureProvenance,
    DesktopCaptureSource,
    DesktopCaptureStatus,
)
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect


class WindowsCaptureRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    capture_id: str = Field(min_length=1, max_length=128)
    source: DesktopCaptureSource
    region: ScreenRect | None = None
    process_id: int | None = Field(default=None, ge=1)
    window_handle: int | None = Field(default=None, ge=1)
    process_started_at: datetime | None = None
    max_pixels: int = Field(default=8_294_400, ge=1, le=8_294_400)
    max_bytes: int = Field(default=16_777_216, ge=1, le=16_777_216)

    @field_validator("process_started_at")
    @classmethod
    def validate_process_started_at(cls, value: datetime | None) -> datetime | None:
        return require_aware(value, "process_started_at") if value is not None else None

    @model_validator(mode="after")
    def validate_source(self) -> WindowsCaptureRequest:
        window_fields = (self.process_id, self.window_handle, self.process_started_at)
        if self.source is DesktopCaptureSource.WINDOW:
            if self.region is not None or any(value is None for value in window_fields):
                raise ValueError("window capture requires native process/window identity")
        elif self.region is None or any(value is not None for value in window_fields):
            raise ValueError("region capture requires only a rectangle")
        return self


class WindowsCaptureReply(StrictModel):
    status: DesktopCaptureStatus
    captured_at: datetime | None = None
    region: ScreenRect | None = None
    process_id: int | None = Field(default=None, ge=1)
    window_handle: int | None = Field(default=None, ge=1)
    process_started_at: datetime | None = None
    png_base64: str = Field(default="", max_length=22_369_624)

    @field_validator("captured_at", "process_started_at")
    @classmethod
    def validate_time(cls, value: datetime | None, info: object) -> datetime | None:
        if value is None:
            return None
        return require_aware(value, getattr(info, "field_name", "timestamp"))

    @model_validator(mode="after")
    def validate_payload(self) -> WindowsCaptureReply:
        populated = (
            self.captured_at is not None and self.region is not None and bool(self.png_base64)
        )
        if (self.status is DesktopCaptureStatus.OK) != populated:
            raise ValueError("successful helper reply requires exactly one PNG payload")
        if self.status is not DesktopCaptureStatus.OK and any(
            value is not None
            for value in (self.process_id, self.window_handle, self.process_started_at)
        ):
            raise ValueError("failed helper replies cannot contain native identity")
        return self


class WindowsCaptureBridge:
    """One capture per helper process; timeout/cancellation always kills and reaps it."""

    frame_provenance: DesktopCaptureProvenance = "windows_gdi_on_demand"

    def __init__(
        self,
        executable: Path,
        *,
        timeout: float = 5.0,
        output_limit: int = 24 * 1024 * 1024,
    ) -> None:
        if not 0 < timeout <= 30:
            raise ValueError("capture timeout must be between 0 and 30 seconds")
        if not 1_048_576 <= output_limit <= 32 * 1024 * 1024:
            raise ValueError("capture output limit must be between 1 MiB and 32 MiB")
        self.executable = executable.resolve()
        self.timeout = timeout
        self.output_limit = output_limit
        self._busy = False

    async def list_monitors(
        self,
    ) -> tuple[tuple[MonitorDescriptor, ...], str, tuple[int, int] | None]:
        """Read physical monitor bounds and the cursor's location from the capture helper."""
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable), "--list-monitors",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                assert process.stdout is not None
                raw = await process.stdout.readline()
                if len(raw) > 8192 or await process.stdout.read(1):
                    raise ValueError("invalid monitor response")
                await process.wait()
                if process.returncode != 0:
                    raise ValueError("monitor query failed")
                payload = json.loads(raw)
                records = payload.get("monitors") if isinstance(payload, dict) else None
                if not isinstance(records, list) or not 1 <= len(records) <= 16:
                    raise ValueError("invalid monitor list")
                monitors = tuple(MonitorDescriptor.model_validate(item) for item in records)
                if sum(monitor.primary for monitor in monitors) != 1:
                    raise ValueError("monitor list has no unique primary")
                cursor_monitor_id = payload.get("cursor_monitor_id")
                if cursor_monitor_id not in {monitor.id for monitor in monitors}:
                    raise ValueError("cursor monitor is missing")
                cursor_x = payload.get("cursor_x")
                cursor_y = payload.get("cursor_y")
                cursor_point = (
                    (cursor_x, cursor_y)
                    if isinstance(cursor_x, int) and not isinstance(cursor_x, bool)
                    and isinstance(cursor_y, int) and not isinstance(cursor_y, bool)
                    else None
                )
                return monitors, cursor_monitor_id, cursor_point
        except (TimeoutError, OSError, ValueError, UnicodeError) as exc:
            raise ValueError("native monitor query unavailable") from exc
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()

    async def capture(self, request: WindowsCaptureRequest) -> WindowsCaptureReply:
        if self._busy:
            return WindowsCaptureReply(status=DesktopCaptureStatus.BUSY)
        self._busy = True
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=self.output_limit,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if key.upper()
                        in {
                            "SYSTEMROOT",
                            "WINDIR",
                            "PATH",
                            "TEMP",
                            "TMP",
                            "DOTNET_ROOT",
                        }
                    },
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(request.model_dump_json().encode() + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                line = await process.stdout.readline()
                if len(line) >= self.output_limit or await process.stdout.read(1):
                    return WindowsCaptureReply(status=DesktopCaptureStatus.PROTOCOL_ERROR)
                await process.wait()
                if process.returncode != 0:
                    return WindowsCaptureReply(status=DesktopCaptureStatus.UNAVAILABLE)
                return WindowsCaptureReply.model_validate_json(line)
        except TimeoutError:
            return WindowsCaptureReply(status=DesktopCaptureStatus.TIMEOUT)
        except (ValueError, UnicodeError, asyncio.LimitOverrunError):
            return WindowsCaptureReply(status=DesktopCaptureStatus.PROTOCOL_ERROR)
        except OSError:
            return WindowsCaptureReply(status=DesktopCaptureStatus.UNAVAILABLE)
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            self._busy = False
