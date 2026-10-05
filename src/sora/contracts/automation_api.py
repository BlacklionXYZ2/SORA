"""Owner-local canonical automation storage; no worker availability inferred from a save."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from sora.contracts.automation import (
    AutomationDefinition,
    AutomationOccurrence,
    AutomationSlot,
    AutomationSpec,
    Version,
)
from sora.contracts.base import ContractModel, Identifier, require_aware

type SchedulerState = Literal["unavailable", "running", "degraded", "stopping", "stopped"]


class AutomationCreate(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    spec: AutomationSpec
    state: Literal["active", "paused"] = "paused"


class AutomationChange(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    expected_version: Version
    action: Literal["edit", "pause", "resume", "delete"]
    spec: AutomationSpec | None = None

    @model_validator(mode="after")
    def edit_only(self) -> AutomationChange:
        if (self.action == "edit") != (self.spec is not None):
            raise ValueError("Edit requires a complete spec; other actions cannot replace it")
        return self


class AutomationRunNow(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    expected_version: Version
    action: Literal["run_now"] = "run_now"


class AutomationAck(ContractModel):
    instance_id: uuid.UUID
    committed_instance_id: uuid.UUID
    request_id: uuid.UUID
    action: Literal["create", "edit", "pause", "resume", "delete", "run_now"]
    definition: AutomationDefinition
    next_slot: AutomationSlot | None
    occurrence: AutomationOccurrence | None = None
    projection_revision: int = Field(strict=True, ge=0)
    event_id: Identifier
    replayed: bool = Field(default=False, strict=True)
    scheduler_state: SchedulerState = "unavailable"
    note: str = "Historical saved receipt, not execution or current definition state."

    @model_validator(mode="after")
    def manual_only(self) -> AutomationAck:
        if (self.action == "run_now") != (self.occurrence is not None):
            raise ValueError("Only Run now receipts contain an occurrence")
        value = self.occurrence
        if value is not None and (
            value.origin != "manual"
            or value.automation_id != self.definition.automation_id
            or value.definition_version != self.definition.entity_version
            or value.behavior != self.definition.spec.behavior
            or value.task_id is not None
            or value.status not in {"reserved", "skipped", "blocked"}
            or value.slot.slot_key != "manual:" + str(self.request_id)
        ):
            raise ValueError("Invalid historical manual reservation receipt")
        return self


class AutomationDetail(ContractModel):
    instance_id: uuid.UUID
    projection_revision: int = Field(strict=True, ge=0)
    definition: AutomationDefinition
    next_slot: AutomationSlot | None
    scheduler_state: SchedulerState = "unavailable"


class AutomationSummary(ContractModel):
    automation_id: Identifier
    name: str = Field(min_length=1, max_length=128)
    state: Literal["active", "paused"]
    entity_version: Version
    trigger_kind: Literal["once", "daily", "weekly", "interval"]
    timezone: str = Field(min_length=1, max_length=64)
    next_slot: AutomationSlot | None


class AutomationPage(ContractModel):
    instance_id: uuid.UUID
    projection_revision: int = Field(strict=True, ge=0)
    observed_at: datetime
    automations: tuple[AutomationSummary, ...] = Field(max_length=50)
    next_cursor: str | None = Field(default=None, max_length=4096)
    scheduler_state: SchedulerState = "unavailable"

    @model_validator(mode="after")
    def aware(self) -> AutomationPage:
        require_aware(self.observed_at, "observed_at")
        return self


class AutomationHistory(ContractModel):
    instance_id: uuid.UUID
    projection_revision: int = Field(strict=True, ge=0)
    automation_id: Identifier
    occurrences: tuple[AutomationOccurrence, ...] = Field(max_length=50)
    next_cursor: str | None = Field(default=None, max_length=4096)
