from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sora.contracts.models import (
    ApprovalRequest,
    ApprovalStatus,
    CapabilityGrant,
    CapabilityOperation,
    CapabilityRequest,
)
from sora.runtime.service import SoraRuntime
from sora.security.operations import OperationAuthorization
from sora.security.policy import authorize


def make_operation_authorization(
    resource: str,
    *,
    grant_id: str = "grant-operation",
    owner_id: str = "owner-local",
    device_id: str = "device-local",
    project_id: str = "project-sora",
    actor_id: str = "operator-alice",
    operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE,
) -> OperationAuthorization:
    now = datetime.now(UTC)
    capability = CapabilityRequest(
        request_id=f"approved-{grant_id}",
        owner_id=owner_id,
        device_id=device_id,
        project_id=project_id,
        operation=operation,
        resource=resource,
    )
    approval = ApprovalRequest(
        approval_id=f"approval-{grant_id}",
        capability=capability,
        status=ApprovalStatus.APPROVED,
        created_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=2),
        decided_at=now - timedelta(seconds=30),
        decided_by=actor_id,
    )
    grant = CapabilityGrant(
        grant_id=grant_id,
        owner_id=owner_id,
        device_id=device_id,
        project_id=project_id,
        operation=operation,
        resource=resource,
        issued_at=now - timedelta(seconds=30),
        not_before=now - timedelta(seconds=30),
        expires_at=now + timedelta(hours=1),
        approval_id=approval.approval_id,
    )
    request = capability.model_copy(update={"request_id": f"request-{grant_id}"})
    decision = authorize(request, grant, evaluated_at=now)
    return OperationAuthorization(
        request=request,
        grant=grant,
        approval=approval,
        decision=decision,
    )


async def persist_operation_grant(
    runtime: SoraRuntime,
    resource: str,
    *,
    grant_id: str = "grant-operation",
    device_id: str = "device-local",
    actor_id: str = "operator-alice",
    operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE,
) -> OperationAuthorization:
    authorization = make_operation_authorization(
        resource,
        grant_id=grant_id,
        owner_id=runtime.config.owner_id,
        device_id=device_id,
        project_id=runtime.config.project_id,
        actor_id=actor_id,
        operation=operation,
    )
    await runtime.repository.save_approval(authorization.approval)
    await runtime.repository.save_grant(authorization.grant)
    return authorization
