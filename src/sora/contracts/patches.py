"""Pure preflight for patch idempotency and entity-version conflicts."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from enum import StrEnum

from pydantic import Field

from .base import StrictModel
from .models import PatchEnvelope

EntityKey = tuple[str, str]


class PatchDisposition(StrEnum):
    APPLICABLE = "applicable"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


class PatchConflict(StrictModel):
    entity_type: str
    entity_id: str
    expected_version: int
    actual_version: int | None


class PatchEvaluation(StrictModel):
    disposition: PatchDisposition
    conflicts: tuple[PatchConflict, ...] = Field(default_factory=tuple)


def evaluate_patch(
    patch: PatchEnvelope,
    *,
    applied_idempotency_keys: Collection[str],
    entity_versions: Mapping[EntityKey, int],
) -> PatchEvaluation:
    """Evaluate without mutating state; persistence rechecks this in its future transaction."""

    if patch.idempotency_key in applied_idempotency_keys:
        return PatchEvaluation(disposition=PatchDisposition.DUPLICATE)

    conflicts = tuple(
        PatchConflict(
            entity_type=precondition.entity_type,
            entity_id=precondition.entity_id,
            expected_version=precondition.expected_version,
            actual_version=entity_versions.get((precondition.entity_type, precondition.entity_id)),
        )
        for precondition in patch.preconditions
        if entity_versions.get((precondition.entity_type, precondition.entity_id))
        != precondition.expected_version
    )
    if conflicts:
        return PatchEvaluation(disposition=PatchDisposition.CONFLICT, conflicts=conflicts)
    return PatchEvaluation(disposition=PatchDisposition.APPLICABLE)
