"""Versioned contracts for scoped desktop-object embodiment affordances."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field, JsonValue, model_validator

from .base import ContractModel, Identifier, NonEmptyText
from .embodiment import ScreenRect


class DesktopObjectAffordance(StrEnum):
    """Small semantic vocabulary understood by the generic embodiment bridge."""

    LOOK = "look"
    POINT = "point"
    TOUCH = "touch"


class DesktopObjectAffordanceRequest(ContractModel):
    """Request one advertised physical presentation without mutating object state."""

    request_id: Identifier
    object_id: Identifier
    affordance: DesktopObjectAffordance
    expected_version: Annotated[int, Field(ge=0)]


class DesktopObjectProjection(ContractModel):
    """Visibility-filtered object data safe for one resolved capability scope."""

    object_id: Identifier
    object_type: Identifier
    label: NonEmptyText
    anchor: NonEmptyText
    rect: ScreenRect
    topology_revision: Annotated[int, Field(ge=1)]
    affordances: tuple[DesktopObjectAffordance, ...] = ()
    content: dict[str, JsonValue] = Field(default_factory=dict)
    canonical_ref: Identifier | None = None
    version: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_affordances(self) -> DesktopObjectProjection:
        if len(self.affordances) != len(set(self.affordances)):
            raise ValueError("desktop-object affordances must be unique")
        return self
