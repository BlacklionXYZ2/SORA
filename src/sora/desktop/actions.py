"""Killable, one-request Windows worker for authorized Level 3 desktop effects."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from sora.contracts.base import StrictModel, require_aware


class WindowsPressRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["press"] = "press"
    process_id: int = Field(ge=1, le=2**32 - 1)
    process_started_at: datetime
    root_window_handle: int = Field(ge=1, le=2**63 - 1)
    native_window_handle: int = Field(ge=0, le=2**63 - 1)
    runtime_id: tuple[int, ...] = Field(default=(), max_length=32)
    automation_id: str = Field(max_length=256)
    control_type: str = Field(min_length=1, max_length=128)
    expected_x: int
    expected_y: int
    expected_width: int = Field(ge=1)
    expected_height: int = Field(ge=1)
    expected_name_before: str = Field(max_length=256)
    expected_name_after: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_identity(self) -> WindowsPressRequest:
        require_aware(self.process_started_at, "process_started_at")
        if not self.runtime_id and not self.native_window_handle and not self.automation_id:
            raise ValueError("press request requires a reusable UIA identity")
        if any(value < 0 for value in self.runtime_id):
            raise ValueError("runtime_id components must be non-negative")
        if self.expected_name_before == self.expected_name_after:
            raise ValueError("press verification must describe a changed postcondition")
        return self


class WindowsTypeRequest(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    operation: Literal["type"] = "type"
    process_id: int = Field(ge=1, le=2**32 - 1)
    process_started_at: datetime
    root_window_handle: int = Field(ge=1, le=2**63 - 1)
    native_window_handle: int = Field(ge=0, le=2**63 - 1)
    runtime_id: tuple[int, ...] = Field(default=(), max_length=32)
    automation_id: str = Field(max_length=256)
    control_type: str = Field(min_length=1, max_length=128)
    expected_x: int
    expected_y: int
    expected_width: int = Field(ge=1)
    expected_height: int = Field(ge=1)
    expected_name_before: str = Field(max_length=256)
    text: str = Field(min_length=1, max_length=4096)

    @model_validator(mode="after")
    def validate_identity(self) -> WindowsTypeRequest:
        require_aware(self.process_started_at, "process_started_at")
        if not self.runtime_id and not self.native_window_handle and not self.automation_id:
            raise ValueError("type request requires a reusable UIA identity")
        if any(value < 0 for value in self.runtime_id):
            raise ValueError("runtime_id components must be non-negative")
        return self


class WindowsActionReply(StrictModel):
    status: Literal[
        "verified",
        "unsupported",
        "unavailable",
        "ambiguous",
        "access_denied",
        "elevated_target",
        "invalid_request",
        "timeout",
        "protocol_error",
        "unknown_outcome",
    ]
    effect_attempted: bool = False
    verified: bool = False

    @model_validator(mode="after")
    def validate_evidence(self) -> WindowsActionReply:
        if self.verified != (self.status == "verified"):
            raise ValueError("verified status and evidence must agree")
        if self.verified and not self.effect_attempted:
            raise ValueError("a verified effect must have been attempted")
        if self.status == "unknown_outcome" and not self.effect_attempted:
            raise ValueError("unknown outcome requires a possible effect attempt")
        return self


class WindowsActionBridge:
    """Runs one isolated native effect and never retries it."""

    def __init__(self, executable: Path, *, timeout: float = 3.0) -> None:
        self.executable = executable.resolve()
        self.timeout = timeout
        self._busy = False

    async def press(self, request: WindowsPressRequest) -> WindowsActionReply:
        if self._busy:
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        self._busy = True
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=16 * 1024,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if key.upper()
                        in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "DOTNET_ROOT"}
                    },
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(request.model_dump_json().encode() + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                line = await process.stdout.readline()
                if await process.stdout.read(1):
                    return WindowsActionReply(
                        status="unknown_outcome", effect_attempted=True
                    )
                await process.wait()
                if process.returncode != 0:
                    return WindowsActionReply(
                        status="unknown_outcome", effect_attempted=True
                    )
                return WindowsActionReply.model_validate_json(line)
        except TimeoutError:
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        except (ValueError, UnicodeError):
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        except OSError:
            return WindowsActionReply(
                status="unknown_outcome" if process is not None else "unavailable",
                effect_attempted=process is not None,
            )
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            self._busy = False


class WindowsTypeBridge:
    """Runs one isolated semantic text replacement and never retries it."""

    def __init__(self, executable: Path, *, timeout: float = 3.0) -> None:
        self.executable = executable.resolve()
        self.timeout = timeout
        self._busy = False

    async def type_text(self, request: WindowsTypeRequest) -> WindowsActionReply:
        if self._busy:
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        self._busy = True
        process: asyncio.subprocess.Process | None = None
        try:
            async with asyncio.timeout(self.timeout):
                process = await asyncio.create_subprocess_exec(
                    str(self.executable),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    limit=32 * 1024,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                    env={
                        key: value
                        for key, value in os.environ.items()
                        if key.upper()
                        in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "DOTNET_ROOT"}
                    },
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(request.model_dump_json().encode() + b"\n")
                await process.stdin.drain()
                process.stdin.close()
                line = await process.stdout.readline()
                if await process.stdout.read(1):
                    return WindowsActionReply(
                        status="unknown_outcome", effect_attempted=True
                    )
                await process.wait()
                if process.returncode != 0:
                    return WindowsActionReply(
                        status="unknown_outcome", effect_attempted=True
                    )
                return WindowsActionReply.model_validate_json(line)
        except TimeoutError:
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        except (ValueError, UnicodeError):
            return WindowsActionReply(status="unknown_outcome", effect_attempted=True)
        except OSError:
            return WindowsActionReply(
                status="unknown_outcome" if process is not None else "unavailable",
                effect_attempted=process is not None,
            )
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                await process.wait()
            self._busy = False
