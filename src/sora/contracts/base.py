"""Shared validation primitives for public contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION: Literal["1.0"] = "1.0"
type ContractVersion = Literal["1.0"]
type Identifier = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
type NonEmptyText = Annotated[str, Field(min_length=1, max_length=16_384)]


class StrictModel(BaseModel):
    """Immutable model that rejects fields outside its declared contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ContractModel(StrictModel):
    """Strict model carrying the current public contract version."""

    schema_version: ContractVersion = CONTRACT_VERSION


def require_aware(value: datetime, field_name: str) -> datetime:
    """Reject local/ambiguous timestamps at contract boundaries."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a UTC offset")
    return value
