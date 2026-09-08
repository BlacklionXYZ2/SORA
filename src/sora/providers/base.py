"""Backend-neutral asynchronous provider protocol."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderRequest,
)


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
