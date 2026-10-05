"""Validated repository projections for identity and memory."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from sora.contracts.base import Identifier, NonEmptyText, StrictModel, require_aware


class MemoryState(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class IdentityRevisionRecord(StrictModel):
    identity_revision_id: Identifier
    owner_id: Identifier
    version: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64)
    source: NonEmptyText
    activated_at: datetime
    files: dict[str, str]

    @field_validator("activated_at")
    @classmethod
    def validate_activated_at(cls, value: datetime) -> datetime:
        return require_aware(value, "activated_at")


class StoredMemory(StrictModel):
    memory_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    content: NonEmptyText
    scope: NonEmptyText
    sensitivity: str
    retention: str
    provenance: NonEmptyText
    evidence_refs: tuple[Identifier, ...] = ()
    entity_version: int = Field(ge=1)
    state: MemoryState
    valid_until: datetime | None = None
    superseded_by: Identifier | None = None
    deleted_at: datetime | None = None

    @field_validator("valid_until", "deleted_at")
    @classmethod
    def validate_optional_time(cls, value: datetime | None) -> datetime | None:
        return require_aware(value, "memory timestamp") if value is not None else None


class MessageRecord(StrictModel):
    message_id: Identifier
    conversation_id: Identifier
    owner_id: Identifier
    project_id: Identifier | None = None
    role: str
    content: NonEmptyText
    provenance: NonEmptyText
    sensitivity: str = "normal"
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return require_aware(value, "created_at")


class VoiceTurnReceipt(StrictModel):
    utterance_key: Identifier
    transcript_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    user_message: MessageRecord
    assistant_message: MessageRecord
    created: bool
