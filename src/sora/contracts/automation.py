"""Closed scheduler data; definitions authorize no task or external effect by themselves."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from sora.contracts.base import ContractModel, Identifier, NonEmptyText, StrictModel, require_aware

type Version = Annotated[int, Field(strict=True, ge=1, le=9_223_372_036_854_775_807)]
type Weekday = Annotated[int, Field(strict=True, ge=0, le=6)]

MANUAL_ADMISSION_SECONDS = 300


class ZonedTrigger(StrictModel):
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Choose an available IANA timezone") from exc
        return value


class OneOffTrigger(ZonedTrigger):
    kind: Literal["once"]
    at: datetime

    @field_validator("at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "at")


class DailyTrigger(ZonedTrigger):
    kind: Literal["daily"]
    local_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


class WeeklyTrigger(ZonedTrigger):
    kind: Literal["weekly"]
    local_time: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    weekdays: tuple[Weekday, ...] = Field(min_length=1, max_length=7)

    @field_validator("weekdays")
    @classmethod
    def unique_days(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if len(set(value)) != len(value):
            raise ValueError("Choose each weekday at most once; Monday is0")
        return tuple(sorted(value))


class IntervalTrigger(ZonedTrigger):
    kind: Literal["interval"]
    anchor_at: datetime
    seconds: int = Field(strict=True, ge=60, le=31_536_000)

    @field_validator("anchor_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "anchor_at")


type AutomationTrigger = Annotated[
    OneOffTrigger | DailyTrigger | WeeklyTrigger | IntervalTrigger,
    Field(discriminator="kind"),
]


class AutomationBehavior(StrictModel):
    kind: Literal["agent_task"] = "agent_task"
    intent: NonEmptyText
    provider: Identifier = "auto"
    model: str | None = Field(default=None, min_length=1, max_length=256)
    effort: str | None = Field(default=None, min_length=1, max_length=32)
    working_directory: str | None = Field(default=None, min_length=1, max_length=2048)
    workspace_mode: Literal["workspace", "worktree"] | None = None

    @field_validator("intent")
    @classmethod
    def visible_intent(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Automation behavior must contain visible text")
        return value


class AutomationSpec(ContractModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    trigger: AutomationTrigger
    behavior: AutomationBehavior
    missed_policy: Literal["skip", "run_once"] = "skip"
    catch_up_seconds: int = Field(default=300, strict=True, ge=0, le=86_400)
    overlap_policy: Literal["skip"] = "skip"

    @field_validator("name")
    @classmethod
    def visible_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Automation name must contain visible text")
        return value


class AutomationDefinition(ContractModel):
    automation_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None
    entity_version: Version
    state: Literal["active", "paused", "deleted"]
    spec: AutomationSpec
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "definition timestamp")

    @model_validator(mode="after")
    def ordered(self) -> AutomationDefinition:
        if self.updated_at.astimezone(UTC) < self.created_at.astimezone(UTC):
            raise ValueError("updated_at precedes created_at")
        return self


class AutomationSlot(ContractModel):
    slot_key: str = Field(min_length=1, max_length=128)
    decision_at: datetime
    planned_local: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$")
    timezone: str = Field(min_length=1, max_length=64)
    disposition: Literal["due", "skip_nonexistent"] = "due"

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        return ZonedTrigger.known_timezone(value)

    @field_validator("planned_local")
    @classmethod
    def real_date(cls, value: str) -> str:
        datetime.fromisoformat(value)
        return value

    @field_validator("decision_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "decision_at")


class AutomationOccurrence(ContractModel):
    occurrence_id: Identifier
    automation_id: Identifier
    definition_version: Version
    origin: Literal["scheduled", "manual"]
    slot: AutomationSlot
    status: Literal["reserved", "admitted", "skipped", "blocked", "failed", "unknown", "completed"]
    behavior: AutomationBehavior
    task_id: Identifier | None = None
    run_id: Identifier | None = None
    reason: str | None = Field(default=None, max_length=256)
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        return require_aware(value, "recorded_at")

    @model_validator(mode="after")
    def linked(self) -> AutomationOccurrence:
        if (self.task_id is None) != (self.run_id is None):
            raise ValueError("Task and run linkage must be recorded together")
        if self.status in {"admitted", "completed"} and self.task_id is None:
            raise ValueError("Admission/completion requires actual task/run evidence")
        if self.status in {"reserved", "skipped", "blocked"} and self.task_id is not None:
            raise ValueError("Unadmitted/skipped/blocked occurrences cannot claim a task")
        if self.slot.disposition == "skip_nonexistent" and self.status not in {
            "skipped",
            "reserved",
        }:
            raise ValueError("A nonexistent local slot cannot admit a task")
        return self
