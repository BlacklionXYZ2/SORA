"""Owner-local semantic Memory presentation, not desktop-coordinate authority."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from sora.contracts.base import ContractModel, Identifier, require_aware
from sora.contracts.embodiment import ScreenRect

type Generation = Annotated[int, Field(ge=0, le=9223372036854775807, strict=True)]
type PresentationStatus = Literal[
    "pending", "selected", "already-visible", "deferred", "unavailable", "rejected", "expired"
]
type PresentationReason = Literal[
    "queued",
    "host-acknowledged",
    "host-deferred",
    "host-unavailable",
    "host-rejected",
    "target-changed",
    "deadline",
    "host-lost",
    "turn-cancelled",
]


class UiHostRegistration(ContractModel):
    instance_id: uuid.UUID
    host_id: uuid.UUID
    profile_key: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    lease_id: uuid.UUID | None = None
    registry_generation: Generation
    panels: tuple[Literal["memory"], ...] = ("memory",)


class UiHostLease(ContractModel):
    instance_id: uuid.UUID
    host_id: uuid.UUID
    lease_id: uuid.UUID
    registry_generation: Generation
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        return require_aware(value, "expires_at")


class UiHostCommand(ContractModel):
    instance_id: uuid.UUID
    host_id: uuid.UUID
    lease_id: uuid.UUID


class UiMemoryCommand(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    memory_id: Identifier
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class UiMemoryPresentation(UiMemoryCommand):
    host_id: uuid.UUID
    lease_id: uuid.UUID
    registry_generation: Generation
    panel: Literal["memory"] = "memory"
    operation: Literal["select-highlight"] = "select-highlight"
    origin: Literal["owner", "companion"]
    activation: Literal["explicit", "passive"]
    dialogue_request_id: Identifier | None = None
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime) -> datetime:
        return require_aware(value, "expires_at")


class UiPresentationPage(UiHostCommand):
    requests: Annotated[tuple[UiMemoryPresentation, ...], Field(max_length=16)] = ()


class UiPresentationAck(UiHostCommand):
    request_id: uuid.UUID
    memory_id: Identifier
    expected_version: Annotated[int, Field(ge=1, strict=True)]
    registry_generation: Generation
    status: Literal["selected", "already-visible", "deferred", "unavailable", "rejected"]
    panel_visible: Annotated[bool, Field(strict=True)]
    selected_id: Identifier | None = None
    selected_version: Annotated[int, Field(ge=1, strict=True)] | None = None
    highlighted: Annotated[bool, Field(strict=True)] = False
    anchor: ScreenRect | None = None


class UiPresentationResult(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    memory_id: Identifier
    expected_version: Annotated[int, Field(ge=1)]
    status: PresentationStatus
    reason: PresentationReason
    event_id: Identifier | None = None
    registry_generation: Generation | None = None
    dialogue_request_id: Identifier | None = None
