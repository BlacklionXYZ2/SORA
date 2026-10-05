"""Persisted operation authorization shared by Core services and API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pydantic import model_validator

from sora.contracts.base import StrictModel
from sora.contracts.models import (
    ApprovalRequest,
    ApprovalStatus,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityRequest,
)
from sora.security.policy import CapabilityDecision, authorize

if TYPE_CHECKING:
    from sora.persistence.repository import SoraRepository


class OperationAuthorizationError(PermissionError):
    """The requested operation lacks a valid persisted grant and approval."""


class OperationAuthorization(StrictModel):
    """Validated evidence joining an exact request, grant, approval, and decision."""

    request: CapabilityRequest
    grant: CapabilityGrant
    approval: ApprovalRequest
    decision: CapabilityDecision

    @model_validator(mode="after")
    def validate_evidence(self) -> OperationAuthorization:
        if not self.decision.allowed:
            raise ValueError("authorization decision must be allowed")
        if self.decision.request_id != self.request.request_id:
            raise ValueError("authorization decision request mismatch")
        if self.decision.grant_id != self.grant.grant_id:
            raise ValueError("authorization decision grant mismatch")
        if self.grant.approval_id != self.approval.approval_id:
            raise ValueError("grant approval linkage mismatch")
        if self.approval.status is not ApprovalStatus.APPROVED:
            raise ValueError("authorization approval is not approved")
        if not self.approval.decided_by:
            raise ValueError("authorization approval has no deciding actor")
        approved = self.approval.capability
        scope = (
            "owner_id",
            "device_id",
            "project_id",
            "operation",
            "resource",
        )
        if any(getattr(approved, name) != getattr(self.request, name) for name in scope):
            raise ValueError("approval capability scope does not match the operation request")
        return self

    @property
    def authorized_by(self) -> str:
        actor = self.approval.decided_by
        if actor is None:  # Kept defensive despite model validation above.
            raise OperationAuthorizationError("approved authorization has no actor")
        return actor

    def require_scope(
        self,
        resource: str,
        *,
        operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE,
    ) -> None:
        if self.request.operation is not operation:
            raise OperationAuthorizationError(
                f"operation grant must authorize {operation.value}"
            )
        if self.request.resource != resource:
            raise OperationAuthorizationError(
                f"operation grant is scoped to '{self.request.resource}', not '{resource}'"
            )


async def resolve_operation_authorization(
    repository: SoraRepository,
    *,
    grant_id: str,
    owner_id: str,
    device_id: str,
    project_id: str | None,
    resource: str,
    operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE,
    now: datetime | None = None,
) -> OperationAuthorization:
    """Resolve an exact operation grant without trusting request-body identity text."""
    if not grant_id.strip():
        raise OperationAuthorizationError("a persisted grant_id is required")
    evaluated_at = now or datetime.now(UTC)
    grant = await repository.get_grant(grant_id)
    if grant is None:
        raise OperationAuthorizationError(f"grant '{grant_id}' was not found")
    approval = await repository.get_approval(grant.approval_id)
    if approval is None:
        raise OperationAuthorizationError(
            f"approval '{grant.approval_id}' for grant '{grant_id}' was not found"
        )
    if approval.status is not ApprovalStatus.APPROVED or evaluated_at >= approval.expires_at:
        raise OperationAuthorizationError(
            f"approval '{approval.approval_id}' is not currently valid"
        )
    request = CapabilityRequest(
        request_id=f"operation-{grant_id}-{int(evaluated_at.timestamp() * 1_000_000)}",
        owner_id=owner_id,
        device_id=device_id,
        project_id=project_id,
        operation=operation,
        resource=resource,
    )
    decision = authorize(request, grant, evaluated_at=evaluated_at)
    if not decision.allowed:
        raise OperationAuthorizationError(
            f"grant '{grant_id}' denied operation '{resource}': {decision.reason.value}"
        )
    try:
        return OperationAuthorization(
            request=request,
            grant=grant,
            approval=approval,
            decision=decision,
        )
    except ValueError as exc:
        raise OperationAuthorizationError(str(exc)) from exc
