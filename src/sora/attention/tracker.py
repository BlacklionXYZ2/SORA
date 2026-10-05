"""P10.5 volatile cursor, selection, and gesture-to-attention resolution."""

from __future__ import annotations

import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator, model_validator

from sora.contracts.base import ContractModel, Identifier, require_aware
from sora.contracts.embodiment import ScreenRect
from sora.contracts.models import AttentionTarget

from .buffer import CursorRingBuffer, CursorSample
from .gestures import detect_click, detect_hover, recognize_circle


class SelectionSample(ContractModel):
    timestamp: datetime
    rect: ScreenRect
    topology_revision: int = Field(ge=1)
    desktop_target_id: Identifier | None = None
    target_element: Identifier | None = None
    monotonic_ns: int | None = Field(default=None, ge=0)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")


class CursorSampleBatch(ContractModel):
    samples: tuple[CursorSample, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def ordered_samples(self) -> CursorSampleBatch:
        if any(
            current.timestamp < previous.timestamp
            for previous, current in zip(self.samples, self.samples[1:], strict=False)
        ):
            raise ValueError("cursor batch must be timestamp ordered")
        return self


class AttentionResolveRequest(ContractModel):
    source: Literal["hover", "click", "selection", "circle"]
    reference_time: datetime

    @field_validator("reference_time")
    @classmethod
    def validate_reference_time(cls, value: datetime) -> datetime:
        return require_aware(value, "reference_time")


class AttentionResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NO_DATA = "no_data"
    EXPIRED = "expired"
    REJECTED = "rejected"


class AttentionResolution(ContractModel):
    status: AttentionResolutionStatus
    source: Literal["hover", "click", "selection", "circle"]
    reason: str
    target: AttentionTarget | None = None

    @model_validator(mode="after")
    def consistent_target(self) -> AttentionResolution:
        if (self.status is AttentionResolutionStatus.RESOLVED) != (self.target is not None):
            raise ValueError("resolved attention must contain exactly one target")
        return self


class AttentionTracker:
    """Own raw input samples only in process memory; never a persistence repository."""

    def __init__(
        self,
        *,
        cursor_capacity: int = 1_000,
        cursor_max_age_seconds: float = 8.0,
        selection_capacity: int = 32,
        selection_max_age_seconds: float = 8.0,
        target_ttl_seconds: float = 5.0,
    ) -> None:
        if selection_capacity < 1:
            raise ValueError("selection_capacity must be positive")
        if not 0 < selection_max_age_seconds <= 60:
            raise ValueError("selection_max_age_seconds must be between 0 and 60")
        if not 0 < target_ttl_seconds <= 30:
            raise ValueError("target_ttl_seconds must be between 0 and 30")
        self.cursor = CursorRingBuffer(cursor_capacity, cursor_max_age_seconds)
        self.selection_capacity = selection_capacity
        self.selection_max_age_seconds = selection_max_age_seconds
        self.target_ttl_seconds = target_ttl_seconds
        self._selections: deque[SelectionSample] = deque(maxlen=selection_capacity)
        self._latest_selection_seen: datetime | None = None

    @property
    def selection_count(self) -> int:
        return len(self._selections)

    @property
    def latest_selection(self) -> SelectionSample | None:
        return self._selections[-1] if self._selections else None

    def clear(self) -> None:
        self.cursor.clear()
        self._selections.clear()
        self._latest_selection_seen = None

    def append_cursor_batch(self, batch: CursorSampleBatch) -> None:
        self.cursor.append_many(batch.samples)

    def append_selection(self, sample: SelectionSample) -> None:
        if self._selections and sample.timestamp < self._selections[-1].timestamp:
            raise ValueError("selection samples must be appended in timestamp order")
        self._selections.append(sample)
        self._latest_selection_seen = sample.timestamp
        self._prune_selections(sample.timestamp)

    def _prune_selections(self, now: datetime) -> None:
        cutoff = now - timedelta(seconds=self.selection_max_age_seconds)
        while self._selections and self._selections[0].timestamp < cutoff:
            self._selections.popleft()

    def resolve(
        self,
        request: AttentionResolveRequest,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        topology_revision: int,
        now: datetime | None = None,
    ) -> AttentionResolution:
        evaluated_at = now or datetime.now(UTC)
        require_aware(evaluated_at, "now")
        if request.reference_time > evaluated_at + timedelta(seconds=5):
            return self._unresolved(request.source, "rejected", "reference_time_is_future")
        self.cursor.prune(evaluated_at)
        self._prune_selections(evaluated_at)

        if request.source == "selection":
            return self._resolve_selection(
                request,
                owner_id=owner_id,
                device_id=device_id,
                project_id=project_id,
                topology_revision=topology_revision,
                now=evaluated_at,
            )

        newest = self.cursor.newest
        oldest = self.cursor.oldest
        if newest is None or oldest is None:
            if self.cursor.latest_seen is not None:
                return self._unresolved(request.source, "expired", "cursor_samples_expired")
            return self._unresolved(request.source, "no_data", "cursor_buffer_empty")
        if request.reference_time < oldest.timestamp:
            return self._unresolved(request.source, "expired", "reference_predates_buffer")
        if request.reference_time > newest.timestamp + timedelta(seconds=1):
            return self._unresolved(request.source, "expired", "cursor_samples_expired")

        window_seconds = 1.25 if request.source in {"hover", "click"} else 4.0
        samples = tuple(
            sample
            for sample in self.cursor.get_recent_samples(window_seconds, now=request.reference_time)
            if sample.topology_revision == topology_revision
        )
        if not samples:
            return self._unresolved(request.source, "expired", "no_current_topology_samples")

        if request.source == "hover":
            point = detect_hover(samples, min_duration_seconds=0.5, max_distance_px=15)
            if point is None:
                return self._unresolved("hover", "rejected", "hover_thresholds_not_met")
            rect = ScreenRect(x=point[0], y=point[1], width=1, height=1)
            confidence = 0.85
            element = samples[-1].target_element
        elif request.source == "click":
            clicked = detect_click(samples)
            if clicked is None:
                return self._unresolved("click", "rejected", "click_thresholds_not_met")
            rect = ScreenRect(x=clicked.x, y=clicked.y, width=1, height=1)
            confidence = 0.98
            element = clicked.target_element
        else:
            bounds = recognize_circle(samples)
            if bounds is None:
                return self._unresolved("circle", "rejected", "circle_thresholds_not_met")
            rect = ScreenRect(x=bounds[0], y=bounds[1], width=bounds[2], height=bounds[3])
            confidence = 0.9
            element = samples[-1].target_element

        event_expiry = samples[-1].timestamp + timedelta(seconds=self.cursor.max_age_seconds)
        return self._resolved(
            source=request.source,
            rect=rect,
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            topology_revision=topology_revision,
            now=evaluated_at,
            event_expiry=event_expiry,
            confidence=confidence,
            target_element=element,
        )

    def _resolve_selection(
        self,
        request: AttentionResolveRequest,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        topology_revision: int,
        now: datetime,
    ) -> AttentionResolution:
        if not self._selections:
            if self._latest_selection_seen is not None:
                return self._unresolved("selection", "expired", "selection_expired")
            return self._unresolved("selection", "no_data", "selection_buffer_empty")
        eligible = tuple(
            sample
            for sample in self._selections
            if sample.timestamp <= request.reference_time
            and sample.topology_revision == topology_revision
        )
        if not eligible:
            oldest = self._selections[0]
            reason = (
                "reference_predates_buffer"
                if request.reference_time < oldest.timestamp
                else "no_current_topology_samples"
            )
            return self._unresolved("selection", "expired", reason)
        sample = eligible[-1]
        event_expiry = sample.timestamp + timedelta(seconds=self.selection_max_age_seconds)
        if now >= event_expiry:
            return self._unresolved("selection", "expired", "selection_expired")
        return self._resolved(
            source="selection",
            rect=sample.rect,
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            topology_revision=topology_revision,
            now=now,
            event_expiry=event_expiry,
            confidence=1.0,
            target_element=sample.target_element,
            desktop_target_id=sample.desktop_target_id,
        )

    def _resolved(
        self,
        *,
        source: Literal["hover", "click", "selection", "circle"],
        rect: ScreenRect,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        topology_revision: int,
        now: datetime,
        event_expiry: datetime,
        confidence: float,
        target_element: str | None,
        desktop_target_id: str | None = None,
    ) -> AttentionResolution:
        expires_at = min(
            now + timedelta(seconds=self.target_ttl_seconds),
            event_expiry,
        )
        if expires_at <= now:
            return self._unresolved(source, "expired", "source_event_expired")
        target = AttentionTarget(
            target_id=f"attention-{uuid.uuid4()}",
            source=source,
            created_at=now,
            expires_at=expires_at,
            owner_id=owner_id,
            device_id=device_id,
            project_id=project_id,
            ui_element=target_element,
            screen_rect=(rect.x, rect.y, rect.width, rect.height),
            confidence=confidence,
            topology_revision=topology_revision,
            desktop_target_id=desktop_target_id,
            provenance="volatile_local_input",
        )
        return AttentionResolution(
            status=AttentionResolutionStatus.RESOLVED,
            source=source,
            reason="resolved_from_volatile_buffer",
            target=target,
        )

    @staticmethod
    def _unresolved(
        source: Literal["hover", "click", "selection", "circle"],
        status: Literal["no_data", "expired", "rejected"],
        reason: str,
    ) -> AttentionResolution:
        return AttentionResolution(
            status=AttentionResolutionStatus(status),
            source=source,
            reason=reason,
        )
