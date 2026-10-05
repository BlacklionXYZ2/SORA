"""P10.6-P10.7 conversational references and configured content navigation."""

from __future__ import annotations

import string
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from sora.contracts.base import ContractModel, Identifier, NonEmptyText, require_aware
from sora.contracts.embodiment import ScreenRect


class ReferenceKind(StrEnum):
    UI = "ui"
    PROJECT = "project"
    FILE = "file"
    TASK = "task"
    DOCUMENT = "document"
    OBJECT = "object"
    ARTIFACT = "artifact"


class ReferenceCandidate(ContractModel):
    reference_id: Identifier
    kind: ReferenceKind
    label: NonEmptyText
    aliases: tuple[NonEmptyText, ...] = ()
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    created_at: datetime
    expires_at: datetime
    last_referenced_at: datetime
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0
    pinned: bool = False
    attention_target_id: Identifier | None = None
    desktop_target_id: Identifier | None = None
    content_reference_id: Identifier | None = None
    task_id: Identifier | None = None
    object_id: Identifier | None = None
    crop_ref: Identifier | None = None
    vision_evidence_refs: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()
    screen_rect: ScreenRect | None = None
    topology_revision: Annotated[int, Field(ge=1)] | None = None
    spatial_expires_at: datetime | None = None
    provenance: NonEmptyText = "unspecified"

    @model_validator(mode="after")
    def validate_lifetime(self) -> ReferenceCandidate:
        for name in ("created_at", "expires_at", "last_referenced_at"):
            require_aware(getattr(self, name), name)
        if self.spatial_expires_at is not None:
            require_aware(self.spatial_expires_at, "spatial_expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must follow created_at")
        if not any(
            (
                self.attention_target_id,
                self.desktop_target_id,
                self.content_reference_id,
                self.task_id,
                self.object_id,
            )
        ):
            raise ValueError("reference candidate requires a concrete backing reference")
        if self.vision_evidence_refs and self.crop_ref is None:
            raise ValueError("vision evidence references require a scoped crop reference")
        if len(self.vision_evidence_refs) != len(set(self.vision_evidence_refs)):
            raise ValueError("vision evidence references must be unique")
        return self


class ReferenceResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    CLARIFICATION_REQUIRED = "clarification_required"
    EXPIRED = "expired"
    NOT_FOUND = "not_found"
    STALE = "stale"


class ReferenceResolveRequest(ContractModel):
    utterance: NonEmptyText
    explicit_reference_id: Identifier | None = None
    minimum_confidence: Annotated[float, Field(ge=0.5, le=1)] = 0.75


class ReferenceResolution(ContractModel):
    resolution_id: Identifier
    status: ReferenceResolutionStatus
    reason: NonEmptyText
    candidate: ReferenceCandidate | None = None
    alternatives: tuple[ReferenceCandidate, ...] = Field(default=(), max_length=8)
    clarification_marker_queued: bool = False

    @model_validator(mode="after")
    def consistent_candidate(self) -> ReferenceResolution:
        if (self.status is ReferenceResolutionStatus.RESOLVED) != (self.candidate is not None):
            raise ValueError("only resolved references contain a selected candidate")
        if self.status is ReferenceResolutionStatus.RESOLVED and self.alternatives:
            raise ValueError("resolved references cannot contain alternatives")
        return self


class ReferencePinRequest(ContractModel):
    reference_id: Identifier
    ttl_seconds: Annotated[float, Field(gt=0, le=86_400, allow_inf_nan=False)] = 3_600


class ContentReference(ContractModel):
    reference_id: Identifier
    kind: Literal["repository", "file", "document", "image", "telemetry", "artifact"]
    label: NonEmptyText
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    path: Path
    root: Path
    handler_id: Identifier | None = None
    line: Annotated[int, Field(ge=1)] | None = None
    column: Annotated[int, Field(ge=1)] | None = None
    desktop_target_id: Identifier | None = None
    created_at: datetime

    @model_validator(mode="after")
    def validate_paths(self) -> ContentReference:
        require_aware(self.created_at, "created_at")
        if not self.path.is_absolute() or not self.root.is_absolute():
            raise ValueError("content path and root must be absolute")
        return self


class ContentHandlerConfig(ContractModel):
    handler_id: Identifier
    kinds: tuple[Literal["repository", "file", "document", "image", "telemetry", "artifact"], ...]
    executable: Path
    arguments: tuple[str, ...] = ("{path}",)
    verbs: tuple[Literal["open", "show", "where"], ...] = ("open", "show")
    supports_line: bool = False
    supports_column: bool = False
    supports_highlight: bool = False
    completion_timeout_seconds: Annotated[float, Field(ge=0, le=30, allow_inf_nan=False)] = 0

    @model_validator(mode="after")
    def validate_configuration(self) -> ContentHandlerConfig:
        if not self.kinds:
            raise ValueError("content handler requires at least one kind")
        if not self.verbs:
            raise ValueError("content handler requires at least one verb")
        if not self.executable.is_absolute():
            raise ValueError("content handler executable must be absolute")
        allowed = {"path", "line", "column", "reference_id", "verb"}
        fields: set[str] = set()
        formatter = string.Formatter()
        for argument in self.arguments:
            for _, field_name, _, conversion in formatter.parse(argument):
                if conversion:
                    raise ValueError("content handler arguments cannot use conversions")
                if field_name:
                    fields.add(field_name)
        if not fields <= allowed:
            raise ValueError("content handler arguments contain an unsupported placeholder")
        if "path" not in fields:
            raise ValueError("content handler arguments must contain {path}")
        return self


class ContentNavigateRequest(ContractModel):
    utterance: NonEmptyText
    verb: Literal["open", "show", "where"] = "open"
    explicit_reference_id: Identifier | None = None
    line: Annotated[int, Field(ge=1)] | None = None
    column: Annotated[int, Field(ge=1)] | None = None


class ContentNavigationStatus(StrEnum):
    OPENED = "opened"
    OPENED_WITH_LIMITATIONS = "opened_with_limitations"
    CLARIFICATION_REQUIRED = "clarification_required"
    NOT_FOUND = "not_found"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ContentNavigationResult(ContractModel):
    status: ContentNavigationStatus
    reason: NonEmptyText
    resolution: ReferenceResolution
    reference_id: Identifier | None = None
    handler_id: Identifier | None = None
    process_id: int | None = Field(default=None, ge=1)
    limitations: tuple[NonEmptyText, ...] = ()
    presentation_command_id: Identifier | None = None
