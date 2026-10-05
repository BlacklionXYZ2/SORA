"""Bounded read-only Windows observations; observations confer no action authority."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from sora.contracts.base import ContractModel, Identifier, StrictModel, require_aware
from sora.contracts.embodiment import ScreenRect


class DesktopObservationRequest(ContractModel):
    operation: Literal["inventory", "windows", "tree", "text", "selection"]
    process_id: int = Field(default=0, ge=0, le=2**32 - 1)
    window_handle: int | None = Field(default=None, ge=1, le=2**63 - 1)
    max_nodes: int = Field(default=128, ge=1, le=256)
    max_depth: int = Field(default=6, ge=0, le=12)
    max_text_chars: int = Field(default=8192, ge=1, le=32768)

    @model_validator(mode="after")
    def require_window(self) -> DesktopObservationRequest:
        if (self.operation in {"tree", "text", "selection"}) != (self.window_handle is not None):
            raise ValueError("tree/text/selection require a window_handle; lists must omit it")
        if (self.operation == "inventory") != (self.process_id == 0):
            raise ValueError("inventory omits process_id; targeted observations require a process")
        return self

    @property
    def resource(self) -> str:
        return "desktop.observe:inventory" if self.operation == "inventory" else (
            f"desktop.observe:{self.process_id}"
        )


class DesktopNode(StrictModel):
    node_id: str = Field(min_length=1, max_length=128)
    parent_id: str | None = Field(default=None, max_length=128)
    process_id: int = Field(ge=1, le=2**32 - 1)
    window_handle: int = Field(ge=0, le=2**63 - 1)
    name: str = Field(max_length=256)
    automation_id: str = Field(max_length=256)
    control_type: str = Field(max_length=128)
    runtime_id: tuple[int, ...] = Field(default=(), max_length=32)
    rect: ScreenRect | None
    focused: bool
    enabled: bool
    offscreen: bool
    password: bool
    text: str = Field(default="", max_length=32768)
    selected_text: str = Field(default="", max_length=32768)
    text_truncated: bool = False
    text_available: bool = False
    selection_available: bool = False
    process_started_at: datetime | None = None


class DesktopObservation(ContractModel):
    status: Literal[
        "ok", "timeout", "unavailable", "access_denied", "elevated_target",
        "invalid_request", "protocol_error", "not_configured", "busy", "stale_layout",
    ]
    nodes: tuple[DesktopNode, ...] = Field(default=(), max_length=256)
    truncated: bool = False
    topology_revision: int = Field(default=0, ge=0)
    process_started_at: datetime | None = None

    @model_validator(mode="after")
    def consistent_nodes(self) -> DesktopObservation:
        if self.process_started_at is not None:
            require_aware(self.process_started_at, "process_started_at")
        if self.status != "ok" and (self.nodes or self.truncated):
            raise ValueError("failed observations cannot contain usable nodes")
        seen: set[str] = set()
        for node in self.nodes:
            if node.node_id in seen or (node.parent_id is not None and node.parent_id not in seen):
                raise ValueError("nodes must have unique IDs and precede their children")
            if node.password and (node.name or node.text or node.selected_text):
                raise ValueError("password nodes must redact names and text")
            if node.process_started_at is not None:
                require_aware(node.process_started_at, "node process_started_at")
            seen.add(node.node_id)
        return self


class DesktopAuthority(StrEnum):
    """Distinct desktop authority levels implemented through P11.3."""

    OBSERVE = "observe"
    PRESENT = "present"
    NAVIGATE = "navigate"
    INTERACT = "interact"


class DesktopTargetRequest(ContractModel):
    """Acquire one short-lived target from a fresh, process-scoped UIA tree."""

    process_id: int = Field(ge=1, le=2**32 - 1)
    window_handle: int = Field(ge=1, le=2**63 - 1)
    runtime_id: tuple[int, ...] = Field(default=(), max_length=32)
    automation_id: str = Field(default="", max_length=256)
    name: str = Field(default="", max_length=256)
    control_type: str = Field(default="", max_length=128)
    max_nodes: int = Field(default=256, ge=1, le=256)
    max_depth: int = Field(default=12, ge=0, le=12)
    ttl_seconds: float = Field(default=60.0, gt=0, le=300, allow_inf_nan=False)

    @model_validator(mode="after")
    def require_selector(self) -> DesktopTargetRequest:
        if not (self.runtime_id or self.automation_id or self.name):
            raise ValueError("target acquisition requires runtime_id, automation_id, or name")
        if any(value < 0 for value in self.runtime_id):
            raise ValueError("runtime_id components must be non-negative")
        return self

    @property
    def observation_request(self) -> DesktopObservationRequest:
        return DesktopObservationRequest(
            operation="tree",
            process_id=self.process_id,
            window_handle=self.window_handle,
            max_nodes=self.max_nodes,
            max_depth=self.max_depth,
        )


class DesktopTargetRevalidationRequest(ContractModel):
    authority: Literal[DesktopAuthority.PRESENT, DesktopAuthority.NAVIGATE]


class DesktopPresentationVerb(StrEnum):
    WALK = "walk"
    TURN = "turn"
    POINT = "point"


class DesktopPresentationRequest(ContractModel):
    verb: DesktopPresentationVerb
    marker_duration_seconds: float = Field(default=5.0, gt=0, le=30, allow_inf_nan=False)


class DesktopTarget(ContractModel):
    """Volatile target identity; this record is not authorization to act."""

    target_id: Identifier
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    process_id: int = Field(ge=1, le=2**32 - 1)
    process_started_at: datetime
    root_window_handle: int = Field(ge=1, le=2**63 - 1)
    native_window_handle: int = Field(ge=0, le=2**63 - 1)
    runtime_id: tuple[int, ...] = Field(default=(), max_length=32)
    automation_id: str = Field(max_length=256)
    name: str = Field(max_length=256)
    control_type: str = Field(max_length=128)
    rect: ScreenRect
    enabled: bool = True
    topology_revision: int = Field(ge=1)
    created_at: datetime
    expires_at: datetime
    last_validated_at: datetime
    status: Literal[
        "active", "expired", "stale_layout", "unavailable", "ambiguous", "revoked"
    ] = "active"

    @model_validator(mode="after")
    def validate_lifetime(self) -> DesktopTarget:
        for field_name in ("process_started_at", "created_at", "expires_at", "last_validated_at"):
            require_aware(getattr(self, field_name), field_name)
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        if not self.runtime_id and self.native_window_handle == 0 and not self.automation_id:
            raise ValueError("target requires a reusable UIA identity")
        return self


class DesktopPressRequest(ContractModel):
    """One deduplicated Level 3 PRESS contact and its independent postcondition."""

    attempt_id: Identifier
    expected_name_after: str = Field(min_length=1, max_length=256)


class DesktopTypeRequest(ContractModel):
    """One deduplicated Level 3 semantic text replacement and postcondition."""

    attempt_id: Identifier
    text: str = Field(min_length=1, max_length=4096)
    mode: Literal["replace"] = "replace"


class DesktopActionStatus(StrEnum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    UNKNOWN_OUTCOME = "unknown_outcome"


class DesktopActionResult(ContractModel):
    """Persisted safety result for one semantic desktop effect attempt."""

    attempt_id: Identifier
    target_id: Identifier
    action: Literal["press", "type"] = "press"
    status: DesktopActionStatus
    reason: str = Field(min_length=1, max_length=128)
    effect_attempted: bool = False
    verified: bool = False
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_result(self) -> DesktopActionResult:
        require_aware(self.created_at, "created_at")
        require_aware(self.updated_at, "updated_at")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        if self.verified and (
            not self.effect_attempted or self.status is not DesktopActionStatus.COMPLETED
        ):
            raise ValueError("verified actions must be attempted and completed")
        if self.status is DesktopActionStatus.COMPLETED and not self.verified:
            raise ValueError("completed actions require independent verification")
        if self.status is DesktopActionStatus.UNKNOWN_OUTCOME and not self.effect_attempted:
            raise ValueError("unknown outcomes require a possible effect attempt")
        return self
