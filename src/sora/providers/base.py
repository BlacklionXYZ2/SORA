"""Backend-neutral asynchronous provider protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderRequest,
)

if TYPE_CHECKING:
    from sora.workspaces.git import GitWorkspaceManager, WorkspaceRecord


class ProviderLaunchError(RuntimeError):
    """A provider could not establish a run."""

    def __init__(self, code: ProviderErrorCode, message: str):
        super().__init__(message)
        self.code = code


class MalformedProviderResult(RuntimeError):
    """Provider output was not valid normalized-result input."""

    def __init__(self, raw_output: str):
        super().__init__("provider returned malformed output")
        self.raw_output = raw_output


def optional_text(data: Mapping[str, object], field_name: str) -> str | None:
    """Read an optional non-empty string from an agent result payload.

    A wrong type is malformed output and is never silently ignored; an empty string is simply
    absent. Used for the agent-authored changelog note, which is optional by design.
    """
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise MalformedProviderResult(f"invalid provider field: {field_name}")
    return value.strip() or None


class ReasoningProvider(Protocol):
    async def capabilities(self) -> ProviderCapabilities: ...

    async def start(self, request: ProviderRequest) -> str: ...

    async def steer(self, run_id: str, instruction: str) -> None: ...

    async def cancel(self, run_id: str) -> None: ...

    async def status(self, run_id: str) -> str: ...

    def events(self, run_id: str) -> AsyncIterator[EventEnvelope]: ...

    async def result(self, run_id: str) -> NormalizedResult: ...

    async def resume(self, session_id: str, request: ProviderRequest) -> str: ...


@runtime_checkable
class SessionProvider(Protocol):
    """Optional native-session identity surface for session-capable providers."""

    async def session_id(self, run_id: str) -> str | None: ...


@runtime_checkable
class OwnedWorkspaceProvider(Protocol):
    """Optional provider surface for binding a coding run to an owned worktree."""

    def for_owned_workspace(
        self,
        record: WorkspaceRecord,
        manager: GitWorkspaceManager,
        *,
        lease_owner: str,
    ) -> ReasoningProvider: ...


@runtime_checkable
class ProjectRootProvider(Protocol):
    """Optional surface for an agent that works directly in an owner-selected project folder.

    Hosted agents are trusted with file writes (owner decision 2026-10-05), so binding only moves
    the agent's working directory. Core still holds the project writer lease and records the
    before/after diff; ``writer_stopped`` tells Core when the agent's process has exited.
    """

    def for_project_root(self, root: str) -> ReasoningProvider: ...

    def writer_stopped(self, run_id: str) -> bool: ...
