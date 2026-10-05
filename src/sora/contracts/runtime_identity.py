"""Owner-local identity for profile-bound desktop clients, not lifecycle authority."""

from typing import Literal

from sora.contracts.base import StrictModel


class RuntimeIdentity(StrictModel):
    version: Literal[1] = 1
    instance_id: str
    state_root: str
    owner_id: str
    project_id: str
