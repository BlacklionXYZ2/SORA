"""P13.1 semantic desktop-event contracts without captured desktop content."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, Identifier, require_aware
from .models import TaskStatus


class DesktopEventKind(StrEnum):
    FOREGROUND_CHANGED = "foreground_changed"
    WINDOW_OPENED = "window_opened"
    WINDOW_CLOSED = "window_closed"
    DIALOG_OPENED = "dialog_opened"
    DIALOG_CLOSED = "dialog_closed"
    TASK_CHANGED = "task_changed"


class DesktopEvent(ContractModel):
    """One content-free event from Windows or SORA's canonical task lifecycle."""

    event_id: Identifier
    kind: DesktopEventKind
    occurred_at: datetime
    topology_revision: int | None = Field(default=None, ge=1)
    process_id: int | None = Field(default=None, ge=1)
    window_handle: int | None = Field(default=None, ge=0)
    task_id: Identifier | None = None
    task_status: TaskStatus | None = None

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return require_aware(value, "occurred_at")

    @model_validator(mode="after")
    def validate_shape(self) -> DesktopEvent:
        if self.kind is DesktopEventKind.TASK_CHANGED:
            if self.task_id is None or self.task_status is None:
                raise ValueError("task_changed events require task_id and task_status")
            if any(
                value is not None
                for value in (self.topology_revision, self.process_id, self.window_handle)
            ):
                raise ValueError("task_changed events cannot contain desktop identity")
            return self

        if self.task_id is not None or self.task_status is not None:
            raise ValueError("desktop events cannot contain task identity")
        if self.topology_revision is None:
            raise ValueError("desktop events require topology_revision")
        if self.kind in {
            DesktopEventKind.WINDOW_OPENED,
            DesktopEventKind.WINDOW_CLOSED,
            DesktopEventKind.DIALOG_OPENED,
            DesktopEventKind.DIALOG_CLOSED,
        } and not self.window_handle:
            raise ValueError(f"{self.kind.value} events require a non-zero window_handle")
        return self


class DesktopEventBatch(ContractModel):
    events: tuple[DesktopEvent, ...] = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def validate_order_and_ids(self) -> DesktopEventBatch:
        if any(
            current.occurred_at < previous.occurred_at
            for previous, current in zip(self.events, self.events[1:], strict=False)
        ):
            raise ValueError("desktop event batches must be timestamp ordered")
        identities: dict[str, DesktopEvent] = {}
        for event in self.events:
            previous = identities.setdefault(event.event_id, event)
            if previous != event:
                raise ValueError("desktop event ID reused with different payload")
        return self


class DesktopEventDisposition(StrEnum):
    ACCEPTED = "accepted"
    DEDUPLICATED = "deduplicated"
    DEBOUNCED = "debounced"


class DesktopAttentionHint(StrEnum):
    NONE = "none"
    NOTICE = "notice"
    IMPORTANT = "important"


class DesktopEventDecision(ContractModel):
    event_id: Identifier
    kind: DesktopEventKind
    disposition: DesktopEventDisposition
    attention_hint: DesktopAttentionHint
    context_invalidated: bool = False
    invalidated_targets: int = Field(default=0, ge=0)
    invalidated_references: int = Field(default=0, ge=0)


class DesktopEventBatchResult(ContractModel):
    decisions: tuple[DesktopEventDecision, ...] = Field(max_length=128)
    accepted_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    debounced_count: int = Field(ge=0)
    context_invalidation_count: int = Field(ge=0)
    inference_requests: int = Field(default=0, ge=0, le=0)
    speech_requests: int = Field(default=0, ge=0, le=0)


class DesktopEventSubscriptionRequest(ContractModel):
    enabled: bool

