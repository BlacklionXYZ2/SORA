"""Capability decisions that cannot be expanded by model or retrieved text."""

from __future__ import annotations

import os
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import Field

from sora.contracts.base import ContractModel, Identifier, require_aware
from sora.contracts.models import (
    ApprovalRequest,
    ApprovalStatus,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityRequest,
    GrantStatus,
)
from sora.contracts.transitions import validate_approval_transition


class DecisionReason(StrEnum):
    ALLOWED = "allowed"
    GRANT_INACTIVE = "grant_inactive"
    NOT_YET_VALID = "not_yet_valid"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    OWNER_MISMATCH = "owner_mismatch"
    DEVICE_MISMATCH = "device_mismatch"
    PROJECT_MISMATCH = "project_mismatch"
    OPERATION_MISMATCH = "operation_mismatch"
    RESOURCE_OUT_OF_SCOPE = "resource_out_of_scope"


class CapabilityDecision(ContractModel):
    request_id: Identifier
    grant_id: Identifier
    allowed: bool
    reason: DecisionReason
    evaluated_at: datetime
    remaining_uses: int | None = Field(default=None, ge=0)


def _path_is_within(requested: str, granted: str) -> bool:
    requested_path = os.path.normcase(str(Path(requested).resolve(strict=False)))
    granted_path = os.path.normcase(str(Path(granted).resolve(strict=False)))
    try:
        return os.path.commonpath((requested_path, granted_path)) == granted_path
    except ValueError:
        return False


def _resource_allowed(request: CapabilityRequest, grant: CapabilityGrant) -> bool:
    if request.operation in {CapabilityOperation.PATH_READ, CapabilityOperation.PATH_WRITE}:
        return _path_is_within(request.resource, grant.resource)
    return request.resource == grant.resource


def authorize(
    request: CapabilityRequest,
    grant: CapabilityGrant,
    *,
    evaluated_at: datetime,
) -> CapabilityDecision:
    """Authorize solely from typed request/grant state; content is never an authority source."""

    require_aware(evaluated_at, "evaluated_at")
    reason = DecisionReason.ALLOWED
    if grant.status is not GrantStatus.ACTIVE:
        reason = DecisionReason.GRANT_INACTIVE
    elif evaluated_at < grant.not_before:
        reason = DecisionReason.NOT_YET_VALID
    elif evaluated_at >= grant.expires_at:
        reason = DecisionReason.EXPIRED
    elif grant.max_uses is not None and grant.used_count >= grant.max_uses:
        reason = DecisionReason.EXHAUSTED
    elif request.owner_id != grant.owner_id:
        reason = DecisionReason.OWNER_MISMATCH
    elif request.device_id != grant.device_id:
        reason = DecisionReason.DEVICE_MISMATCH
    elif request.project_id != grant.project_id:
        reason = DecisionReason.PROJECT_MISMATCH
    elif request.operation is not grant.operation:
        reason = DecisionReason.OPERATION_MISMATCH
    elif not _resource_allowed(request, grant):
        reason = DecisionReason.RESOURCE_OUT_OF_SCOPE

    remaining = None if grant.max_uses is None else max(grant.max_uses - grant.used_count, 0)
    return CapabilityDecision(
        request_id=request.request_id,
        grant_id=grant.grant_id,
        allowed=reason is DecisionReason.ALLOWED,
        reason=reason,
        evaluated_at=evaluated_at,
        remaining_uses=remaining,
    )


def decide_approval(
    approval: ApprovalRequest,
    requested_status: ApprovalStatus,
    *,
    actor_id: str,
    decided_at: datetime,
) -> ApprovalRequest:
    """Move a pending approval to one terminal state, expiring late decisions."""

    require_aware(decided_at, "decided_at")
    effective_status = (
        ApprovalStatus.EXPIRED if decided_at >= approval.expires_at else requested_status
    )
    validate_approval_transition(approval.status, effective_status)
    updated = approval.model_dump()
    updated.update(
        {
            "status": effective_status,
            "decided_at": decided_at,
            "decided_by": actor_id,
        }
    )
    return ApprovalRequest.model_validate(updated)
