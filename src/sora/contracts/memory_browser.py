"""Owner-local canonical Memory projection, never the private capture scratchpad."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator

from sora.contracts.base import ContractModel, Identifier, NonEmptyText, require_aware

type VisibleMemoryState = Literal["active", "expired", "superseded"]
type MemoryFilterState = Literal["active", "expired", "superseded", "all"]
type MemoryProjectFilter = Literal["all", "project", "global"]
type ShortMetadata = Annotated[str, Field(max_length=128)]


class MemoryEvidence(ContractModel):
    reference_id: Identifier
    label: Annotated[str, Field(min_length=1, max_length=512)]
    kind: Literal["repository", "file", "document", "image", "telemetry", "artifact"]


class MemorySummary(ContractModel):
    memory_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    entity_version: Annotated[int, Field(ge=1)]
    state: VisibleMemoryState
    scope: ShortMetadata
    sensitivity: ShortMetadata
    retention: ShortMetadata
    provenance: Annotated[str, Field(max_length=512)]
    metadata_truncated: bool = False
    content_preview: Annotated[str, Field(min_length=1, max_length=512)]
    content_truncated: bool
    valid_until: datetime | None = None

    @field_validator("valid_until")
    @classmethod
    def aware_optional(cls, value: datetime | None) -> datetime | None:
        return require_aware(value, "valid_until") if value else None


class MemoryRecord(MemorySummary):
    content: NonEmptyText
    superseded_by: Identifier | None = None
    evidence: Annotated[tuple[MemoryEvidence, ...], Field(max_length=64)] = ()
    evidence_withheld: bool = False


class MemoryProjection(ContractModel):
    instance_id: uuid.UUID
    owner_id: Identifier
    project_id: Identifier | None = None
    projection_revision: Annotated[int, Field(ge=0)]
    observed_at: datetime
    evidence_note: NonEmptyText

    @field_validator("observed_at")
    @classmethod
    def aware_observed(cls, value: datetime) -> datetime:
        return require_aware(value, "observed_at")


class MemoryPage(MemoryProjection):
    state_filter: MemoryFilterState
    project_filter: MemoryProjectFilter
    scope_filter: ShortMetadata = ""
    query: Annotated[str, Field(max_length=256)] = ""
    limit: Annotated[int, Field(ge=1, le=100)] = 50
    memories: Annotated[tuple[MemorySummary, ...], Field(max_length=100)] = ()
    total: Annotated[int, Field(ge=0)]
    next_cursor: Annotated[str | None, Field(min_length=1, max_length=1024)] = None


class MemoryDetail(MemoryProjection):
    memory: MemoryRecord


class MemoryForget(ContractModel):
    instance_id: uuid.UUID
    request_id: uuid.UUID
    expected_version: Annotated[int, Field(ge=1, strict=True)]


class MemoryCorrection(MemoryForget):
    content: NonEmptyText

    @field_validator("content")
    @classmethod
    def meaningful_content(cls, value: str) -> str:
        if not value.strip() or "\x00" in value:
            raise ValueError("Correction needs meaningful non-NUL text")
        return value


class MemoryMutationAck(ContractModel):
    instance_id: uuid.UUID
    committed_instance_id: uuid.UUID
    request_id: uuid.UUID
    owner_id: Identifier
    project_id: Identifier | None = None
    memory_id: Identifier
    action: Literal["correct", "forget"]
    expected_version: Annotated[int, Field(ge=1)]
    entity_version: Annotated[int, Field(ge=2)]
    successor_id: Identifier | None = None
    successor_version: Literal[1] | None = None
    content_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")] | None = None
    projection_revision: Annotated[int, Field(ge=1)]
    event_id: Identifier
    committed_at: datetime
    replayed: bool = False
    retention_note: NonEmptyText

    @field_validator("committed_at")
    @classmethod
    def aware_committed(cls, value: datetime) -> datetime:
        return require_aware(value, "committed_at")
