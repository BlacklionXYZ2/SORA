"""P13.2 contracts for explicit, bounded, on-demand desktop capture."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, Identifier, require_aware
from .embodiment import ScreenRect

type DesktopCaptureProvenance = Literal["windows_gdi_on_demand", "deterministic_fixture"]


class DesktopCaptureSource(StrEnum):
    WINDOW = "window"
    REGION = "region"


class DesktopCaptureStatus(StrEnum):
    OK = "ok"
    BUSY = "busy"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    ACCESS_DENIED = "access_denied"
    ELEVATED_TARGET = "elevated_target"
    INVALID_REQUEST = "invalid_request"
    PROTOCOL_ERROR = "protocol_error"
    TOO_LARGE = "too_large"
    STALE_LAYOUT = "stale_layout"
    NOT_CONFIGURED = "not_configured"


class DesktopCaptureRequest(ContractModel):
    capture_id: Identifier
    source: DesktopCaptureSource
    topology_revision: int = Field(ge=1)
    desktop_target_id: Identifier | None = None
    region: ScreenRect | None = None
    ttl_seconds: float = Field(default=10.0, gt=0, le=30, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_scope(self) -> DesktopCaptureRequest:
        if self.source is DesktopCaptureSource.WINDOW:
            if self.desktop_target_id is None or self.region is not None:
                raise ValueError("window capture requires only desktop_target_id")
        elif self.region is None or self.desktop_target_id is not None:
            raise ValueError("region capture requires only region")
        return self

    @property
    def resource(self) -> str:
        if self.source is DesktopCaptureSource.WINDOW:
            return f"desktop.capture:window:{self.desktop_target_id}"
        assert self.region is not None
        rect = self.region
        return (
            f"desktop.capture:region:{self.topology_revision}:"
            f"{rect.x},{rect.y},{rect.width},{rect.height}"
        )


class DesktopCaptureFrame(ContractModel):
    capture_id: Identifier
    source: DesktopCaptureSource
    captured_at: datetime
    expires_at: datetime
    topology_revision: int = Field(ge=1)
    region: ScreenRect
    desktop_target_id: Identifier | None = None
    process_id: int | None = Field(default=None, ge=1)
    window_handle: int | None = Field(default=None, ge=1)
    mime_type: Literal["image/png"] = "image/png"
    byte_length: int = Field(ge=1, le=16_777_216)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    image_base64: str = Field(min_length=1, max_length=22_369_624)
    provenance: DesktopCaptureProvenance = "windows_gdi_on_demand"

    @field_validator("captured_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return require_aware(value, field_name)

    @model_validator(mode="after")
    def validate_lifetime_and_source(self) -> DesktopCaptureFrame:
        if self.expires_at <= self.captured_at:
            raise ValueError("capture expiry must follow capture time")
        if self.expires_at > self.captured_at + timedelta(seconds=30):
            raise ValueError("capture retention cannot exceed 30 seconds")
        if self.source is DesktopCaptureSource.WINDOW:
            if (
                self.desktop_target_id is None
                or self.process_id is None
                or self.window_handle is None
            ):
                raise ValueError("window frame requires target and native window identity")
        elif any(
            value is not None
            for value in (self.desktop_target_id, self.process_id, self.window_handle)
        ):
            raise ValueError("region frame cannot contain window identity")
        return self


class DesktopCaptureResult(ContractModel):
    capture_id: Identifier
    status: DesktopCaptureStatus
    frame: DesktopCaptureFrame | None = None

    @model_validator(mode="after")
    def validate_frame(self) -> DesktopCaptureResult:
        if (self.status is DesktopCaptureStatus.OK) != (self.frame is not None):
            raise ValueError("successful capture results contain exactly one frame")
        if self.frame is not None and self.frame.capture_id != self.capture_id:
            raise ValueError("capture result/frame identity mismatch")
        return self
