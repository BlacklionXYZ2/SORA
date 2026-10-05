"""Bounded desktop-host lifecycle contracts; never carry the launch credential."""

from typing import Literal
from uuid import UUID

from sora.contracts.base import StrictModel


class RuntimeLifecycle(StrictModel):
    version: Literal[1] = 1
    instance_id: UUID
    managed_session_id: UUID | None = None
    state: Literal["external", "managed", "shutdown_requested"]
    shutdown_request_id: UUID | None = None


class RuntimeShutdownRequest(StrictModel):
    version: Literal[1] = 1
    managed_session_id: UUID
    request_id: UUID

