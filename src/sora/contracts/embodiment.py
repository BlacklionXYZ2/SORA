"""Embodiment and multi-monitor display topology contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .base import ContractModel, Identifier, StrictModel, require_aware


class ScreenRect(StrictModel):
    """Rectangle in physical screen pixels."""

    x: int
    y: int
    width: Annotated[int, Field(ge=1)]
    height: Annotated[int, Field(ge=1)]

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.right and self.y <= py < self.bottom


class MonitorDescriptor(ContractModel):
    """Authoritative descriptor of a single physical display monitor."""

    id: Identifier
    primary: bool = False
    rect: ScreenRect
    work_area: ScreenRect | None = None
    dpi_scale: Annotated[float, Field(gt=0, allow_inf_nan=False)] = 1.0
    orientation: Literal["landscape", "portrait"] = "landscape"

    @model_validator(mode="after")
    def validate_work_area(self) -> MonitorDescriptor:
        area = self.work_area
        if area is not None and not (
            self.rect.contains(area.x, area.y)
            and self.rect.contains(area.right - 1, area.bottom - 1)
        ):
            raise ValueError("work_area must fit within monitor rect")
        return self


class DisplayTopology(ContractModel):
    """Snapshot of active Windows display layout and virtual desktop bounds."""

    virtual_desktop: ScreenRect
    monitors: tuple[MonitorDescriptor, ...] = ()
    revision: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def validate_topology(self) -> DisplayTopology:
        if not self.monitors:
            return self
        # Verify monitor IDs are unique
        ids = [m.id for m in self.monitors]
        if len(set(ids)) != len(ids):
            raise ValueError("monitor IDs must be unique within topology")
        # Ensure exactly one primary monitor if any monitors are defined
        primary_count = sum(1 for m in self.monitors if m.primary)
        if primary_count != 1:
            raise ValueError(
                f"topology must contain exactly 1 primary monitor, found {primary_count}"
            )
        for monitor in self.monitors:
            if not (
                self.virtual_desktop.contains(monitor.rect.x, monitor.rect.y)
                and self.virtual_desktop.contains(monitor.rect.right - 1, monitor.rect.bottom - 1)
            ):
                raise ValueError("monitor bounds must fit within virtual_desktop")
        return self

    def find_monitor(self, x: int, y: int) -> MonitorDescriptor | None:
        """Find the containing monitor for global virtual desktop coordinates."""
        for m in self.monitors:
            if m.rect.contains(x, y):
                return m
        return None

    def is_point_on_display(self, x: int, y: int) -> bool:
        """Check if global point is inside any physical monitor (not in a gap or offscreen)."""
        return self.find_monitor(x, y) is not None


class VirtualDesktopPoint(StrictModel):
    """Global Windows virtual-desktop coordinate in physical pixels."""

    x: int
    y: int


class MonitorLocalPoint(StrictModel):
    """Physical pixel coordinate relative to a specific monitor origin."""

    monitor_id: Identifier
    x: int
    y: int


class UnityWorldPoint(StrictModel):
    """Continuous coordinate in Unity World Space (meters)."""

    x: Annotated[float, Field(allow_inf_nan=False)]
    y: Annotated[float, Field(allow_inf_nan=False)]
    z: Annotated[float, Field(allow_inf_nan=False)] = 0.0


class EmbodimentPresentationState(StrEnum):
    """High-level semantic presentation state for avatar embodiment."""

    IDLE = "idle"
    MOVING = "moving"
    LOOKING = "looking"
    THINKING = "thinking"
    LISTENING = "listening"
    SPEAKING = "speaking"
    WAITING_FOR_AGENT = "waiting_for_agent"
    READING = "reading"
    TYPING = "typing"
    SITTING = "sitting"
    LEANING = "leaning"
    CLIMBING = "climbing"


class EmbodimentSemanticAction(StrEnum):
    """Presentation-facing action kind; never action authority or effect evidence."""

    POINT = "point"
    PRESS = "press"
    TYPE = "type"
    TOUCH = "touch"
    PLACE_OBJECT = "place_object"


class EmbodimentFeedbackKind(StrEnum):
    """Edge-triggered physical/semantic feedback from the embodiment client."""

    GRABBED = "grabbed"
    RELEASED = "released"
    FELL = "fell"
    LANDED = "landed"
    SUPPORT_REMOVED = "support_removed"
    CLICKED = "clicked"
    POKED = "poked"
    COMPLETED = "completed"
    FAILED = "failed"


class EmbodimentVerb(StrEnum):
    """Action verbs for avatar embodiment commands."""

    MOVE_TO = "move_to"
    LOOK_AT = "look_at"
    SET_STATE = "set_state"
    SHOW_MARKER = "show_marker"
    HIDE_MARKER = "hide_marker"
    PRESENTATION_PHASE = "presentation_phase"
    INTERACTION_START = "interaction_start"
    SET_SUPPORTS = "set_supports"


class EmbodimentSupportSurface(ContractModel):
    """Short-lived selected desktop surface; contains no title, text, or process data."""

    surface_id: Identifier
    kind: Literal["window_top"] = "window_top"
    rect: ScreenRect
    state: Literal["active", "moving", "minimized", "closed", "occluded"] = "active"
    observed_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_lifetime(self) -> EmbodimentSupportSurface:
        require_aware(self.observed_at, "observed_at")
        require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.observed_at:
            raise ValueError("support expiry must be after observation")
        if self.expires_at > self.observed_at + timedelta(seconds=30):
            raise ValueError("support lifetime cannot exceed 30 seconds")
        return self


class EmbodimentCommand(ContractModel):
    """Command from Core to embodiment client directing movement or presentation."""

    command_id: Identifier
    verb: EmbodimentVerb
    target_point: VirtualDesktopPoint | None = None
    target_rect: ScreenRect | None = None
    target_id: Identifier | None = None
    semantic_action_id: Identifier | None = None
    semantic_action: EmbodimentSemanticAction | None = None
    semantic_phase: (
        Literal[
            "navigate",
            "align",
            "reach",
            "contact",
            "verify",
            "retract",
            "completed",
            "cancelled",
            "failed",
        ]
        | None
    ) = None
    presentation_style: Identifier | None = None
    support_surfaces: Annotated[tuple[EmbodimentSupportSurface, ...], Field(max_length=32)] = ()
    marker_duration_seconds: Annotated[float, Field(gt=0, le=30, allow_inf_nan=False)] = 5.0
    state: EmbodimentPresentationState | None = None
    speed_px_per_sec: Annotated[float, Field(gt=0, le=10000, allow_inf_nan=False)] = 150.0
    topology_revision: Annotated[int, Field(ge=1)] = 1
    created_at: datetime

    @model_validator(mode="after")
    def validate_command(self) -> EmbodimentCommand:
        require_aware(self.created_at, "created_at")
        if self.verb == EmbodimentVerb.PRESENTATION_PHASE and (
            self.semantic_action_id is None or self.semantic_phase is None
        ):
            raise ValueError("presentation_phase requires semantic_action_id and semantic_phase")
        if self.verb == EmbodimentVerb.INTERACTION_START and (
            self.target_point is None
            or self.target_rect is None
            or self.target_id is None
            or self.semantic_action_id is None
            or self.semantic_action not in {
                EmbodimentSemanticAction.POINT,
                EmbodimentSemanticAction.PRESS,
                EmbodimentSemanticAction.TYPE,
                EmbodimentSemanticAction.TOUCH,
            }
        ):
            raise ValueError(
                "interaction_start requires target identity/geometry, instance ID and action"
            )
        if (
            self.verb
            in (EmbodimentVerb.MOVE_TO, EmbodimentVerb.LOOK_AT, EmbodimentVerb.SHOW_MARKER)
            and self.target_point is None
        ):
            raise ValueError(f"verb {self.verb} requires target_point")
        if self.target_rect is not None:
            if self.verb not in {
                EmbodimentVerb.SHOW_MARKER,
                EmbodimentVerb.INTERACTION_START,
            }:
                raise ValueError("target_rect requires show_marker or interaction_start")
            if self.target_point is None or not self.target_rect.contains(
                self.target_point.x, self.target_point.y
            ):
                raise ValueError("marker point must be inside target_rect")
        if self.verb == EmbodimentVerb.SET_STATE and self.state is None:
            raise ValueError("verb set_state requires state")
        if self.verb == EmbodimentVerb.SET_STATE and self.state in {
            EmbodimentPresentationState.MOVING,
            EmbodimentPresentationState.LOOKING,
        }:
            raise ValueError("moving and looking are derived from active presentation commands")
        if self.semantic_action is not None and self.verb not in {
            EmbodimentVerb.PRESENTATION_PHASE,
            EmbodimentVerb.INTERACTION_START,
        }:
            raise ValueError("semantic_action requires presentation_phase or interaction_start")
        if self.presentation_style is not None and self.verb not in {
            EmbodimentVerb.SET_STATE,
            EmbodimentVerb.PRESENTATION_PHASE,
            EmbodimentVerb.INTERACTION_START,
        }:
            raise ValueError(
                "presentation_style requires set_state, presentation_phase or interaction_start"
            )
        if self.verb == EmbodimentVerb.SET_SUPPORTS:
            ids = [surface.surface_id for surface in self.support_surfaces]
            if len(ids) != len(set(ids)):
                raise ValueError("support surface IDs must be unique")
        elif self.support_surfaces:
            raise ValueError("support_surfaces requires set_supports")
        return self


class EmbodimentState(ContractModel):
    """Current state of embodiment client reported to Core."""

    visible: bool = True
    interpreted_target_id: Identifier | None = None
    marker_position: VirtualDesktopPoint | None = None
    current_position: VirtualDesktopPoint
    containing_monitor_id: Identifier | None = None
    presentation_state: EmbodimentPresentationState = EmbodimentPresentationState.IDLE
    topology_revision: Annotated[int, Field(ge=1)] = 1
    connected_at: datetime | None = None
    last_seen_at: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> EmbodimentState:
        if self.connected_at is not None:
            require_aware(self.connected_at, "connected_at")
        if self.last_seen_at is not None:
            require_aware(self.last_seen_at, "last_seen_at")
        return self


class EmbodimentFeedbackEvent(ContractModel):
    """Bounded, non-replayed event reported by the currently connected avatar."""

    event_id: Identifier
    kind: EmbodimentFeedbackKind
    occurred_at: datetime
    topology_revision: Annotated[int, Field(ge=1)]
    position: VirtualDesktopPoint
    subject_id: Identifier | None = None
    correlation_id: Identifier | None = None
    detail: Annotated[str | None, Field(max_length=128)] = None
    magnitude: Annotated[float | None, Field(ge=0, le=10000, allow_inf_nan=False)] = None

    @model_validator(mode="after")
    def validate_feedback(self) -> EmbodimentFeedbackEvent:
        require_aware(self.occurred_at, "occurred_at")
        if self.kind in {EmbodimentFeedbackKind.COMPLETED, EmbodimentFeedbackKind.FAILED} and (
            self.correlation_id is None
        ):
            raise ValueError("terminal feedback requires correlation_id")
        if self.kind == EmbodimentFeedbackKind.SUPPORT_REMOVED and self.subject_id is None:
            raise ValueError("support_removed requires subject_id")
        return self
