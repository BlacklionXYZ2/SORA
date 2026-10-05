"""Owner-local static policy; never represented as an approval or a grant."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Literal

from pydantic import StrictBool

from sora.contracts.base import StrictModel
from sora.contracts.models import CapabilityOperation, CapabilityRequest
from sora.security.operations import OperationAuthorization, OperationAuthorizationError


class LocalCompanionPolicy(StrictModel):
    desktop_observe: StrictBool = True
    desktop_capture: StrictBool = True
    file_read: StrictBool = True
    desktop_interact: StrictBool = True
    avatar_control: StrictBool = True
    agent_delegation: StrictBool = True
    direct_file_write: StrictBool = False
    voice: StrictBool = True

    @classmethod
    def disabled(cls) -> LocalCompanionPolicy:
        return cls.model_validate(dict.fromkeys(cls.model_fields, False))

    def require(self, effects: tuple[str, ...]) -> None:
        for effect in effects:
            if effect not in type(self).model_fields:
                raise OperationAuthorizationError("Unregistered local operation effect")
            if not getattr(self, effect):
                raise OperationAuthorizationError(f"{effect} is disabled in Settings")


# Set only by authenticated owner transport or a trusted Core dispatcher. Never read
# a client-supplied origin/device field to choose this branch. ContextVar isolates requests.
_owner_local: ContextVar[bool] = ContextVar("sora_owner_local", default=False)


@contextmanager
def owner_local_scope() -> Iterator[None]:
    token = _owner_local.set(True)
    try:
        yield
    finally:
        _owner_local.reset(token)


def is_owner_local() -> bool:
    return _owner_local.get()


def operation_effects(operation: CapabilityOperation, resource: str) -> tuple[str, ...]:
    """Explicit registered operations, not a blanket tool.invoke permission."""
    if operation is CapabilityOperation.DESKTOP_OBSERVE:
        return ("desktop_capture",) if resource.startswith("desktop.capture:") else (
            "desktop_observe",
        )
    if operation is CapabilityOperation.PATH_READ:
        return ("file_read",)
    if operation is CapabilityOperation.PATH_WRITE:
        return ("direct_file_write",)
    if operation is CapabilityOperation.DESKTOP_INTERACT:
        return ("desktop_interact",)
    if operation is CapabilityOperation.DESKTOP_NAVIGATE:
        return ("desktop_interact",)
    if operation is CapabilityOperation.DESKTOP_PRESENT:
        return ("avatar_control",)
    if operation is CapabilityOperation.VOICE_SESSION:
        return ("voice",)
    if operation is CapabilityOperation.TOOL_INVOKE and resource in {
        "embodiment.command", "embodiment.connect", "embodiment.topology",
    }:
        return ("avatar_control",)
    raise OperationAuthorizationError("This operation has no registered local policy effects")


class LocalPolicyContext(StrictModel):
    request: CapabilityRequest
    effects: tuple[str, ...]
    settings_revision: int
    policy_epoch: int
    audit_source: Literal["owner_policy"] = "owner_policy"

    @property
    def authorized_by(self) -> str:
        return self.request.owner_id

    def require_scope(
        self, resource: str, *, operation: CapabilityOperation = CapabilityOperation.TOOL_INVOKE
    ) -> None:
        if self.request.operation is not operation or self.request.resource != resource:
            raise OperationAuthorizationError("local operation scope mismatch")


OperationContext = OperationAuthorization | LocalPolicyContext
