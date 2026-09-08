"""Deterministic provider with explicit fault modes for hermetic runtime tests."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from enum import StrEnum

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    PatchEnvelope,
    ProposedFact,
    ProposeFactOperation,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderRequest,
)
from sora.providers.base import MalformedProviderResult, ProviderLaunchError


class FaultMode(StrEnum):
    NONE = "none"
    DELAY = "delay"
    FAILURE = "failure"
    RATE_LIMIT = "rate_limit"
    MALFORMED_RESULT = "malformed_result"
    DISCONNECT = "disconnect"
    CANCEL_RACE = "cancel_race"
    UNCERTAIN_LAUNCH = "uncertain_launch"
    UNAVAILABLE = "unavailable"


class DeterministicProvider:
    def __init__(
        self,
        *,
        fault: FaultMode = FaultMode.NONE,
        delay_seconds: float = 0.0,
        supports_steer: bool = True,
    ):
        self.fault = fault
        self.delay_seconds = delay_seconds
        self.supports_steer = supports_steer
        self.start_count = 0
        self._requests: dict[str, ProviderRequest] = {}
        self._tasks: dict[str, asyncio.Task[NormalizedResult]] = {}
        self._cancelled: set[str] = set()
        self._steering: dict[str, list[str]] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="deterministic-mock",
            sessions=False,
            resume=False,
            events=False,
            steer=self.supports_steer,
            cancel=True,
            tool_restrictions=True,
        )

    async def start(self, request: ProviderRequest) -> str:
        self.start_count += 1
        if self.fault is FaultMode.UNAVAILABLE:
            raise ProviderLaunchError(ProviderErrorCode.UNAVAILABLE, "mock provider is unavailable")
        if self.fault is FaultMode.UNCERTAIN_LAUNCH:
            raise ProviderLaunchError(
                ProviderErrorCode.UNCERTAIN_LAUNCH,
                "mock launch acknowledgement was intentionally lost",
            )
        self._requests[request.run_id] = request
        self._tasks[request.run_id] = asyncio.create_task(self._produce(request))
        return request.run_id

    async def result(self, run_id: str) -> NormalizedResult:
        task = self._tasks.get(run_id)
        if task is None:
            raise ProviderLaunchError(
                ProviderErrorCode.LOST_SESSION, f"mock run {run_id} does not exist"
            )
        return await task

    async def cancel(self, run_id: str) -> None:
        self._cancelled.add(run_id)

    async def steer(self, run_id: str, instruction: str) -> None:
        if not self.supports_steer:
            raise NotImplementedError("steering is unsupported")
        self._steering.setdefault(run_id, []).append(instruction)

    async def status(self, run_id: str) -> str:
        task = self._tasks.get(run_id)
        if task is None:
            return "unknown"
        return "completed" if task.done() else "running"

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        del session_id, request
        raise NotImplementedError("mock provider has no native sessions")

    async def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        del run_id
        if False:
            yield EventEnvelope.model_construct()

    async def _produce(self, request: ProviderRequest) -> NormalizedResult:
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if request.run_id in self._cancelled and self.fault is not FaultMode.CANCEL_RACE:
            return self._result(
                request,
                outcome=ProviderOutcome.CANCELLED,
                summary="The deterministic task was cancelled.",
            )
        if self.fault is FaultMode.MALFORMED_RESULT:
            raise MalformedProviderResult('{"outcome":"completed","conclusion":')
        if self.fault is FaultMode.FAILURE:
            return self._failure(request, ProviderErrorCode.INTERNAL, "injected provider failure")
        if self.fault is FaultMode.RATE_LIMIT:
            return self._failure(
                request,
                ProviderErrorCode.RATE_LIMITED,
                "injected rate limit",
                retryable=True,
            )
        if self.fault is FaultMode.DISCONNECT:
            return self._failure(
                request,
                ProviderErrorCode.UNAVAILABLE,
                "injected provider disconnect",
            )

        steering = self._steering.get(request.run_id, [])
        suffix = f" Steering received: {' | '.join(steering)}" if steering else ""
        patch = PatchEnvelope(
            patch_id=f"patch-{request.run_id}",
            source_run_id=request.run_id,
            base_revision=0,
            scope=(
                request.owner_id
                if request.project_id is None
                else f"{request.owner_id}/{request.project_id}"
            ),
            provenance="deterministic mock provider",
            idempotency_key=f"patch-once-{request.run_id}",
            operations=(
                ProposeFactOperation(
                    operation="propose_fact",
                    operation_id=f"fact-{request.run_id}",
                    fact=ProposedFact(
                        content="The deterministic mock completed the requested task.",
                        epistemic_status="observation",
                        confidence=1,
                    ),
                ),
            ),
        )
        return self._result(
            request,
            outcome=ProviderOutcome.COMPLETED,
            summary="The deterministic reasoning task completed.",
            conclusion=f"Processed the task deterministically.{suffix}",
            patch=patch,
        )

    @staticmethod
    def _result(
        request: ProviderRequest,
        *,
        outcome: ProviderOutcome,
        summary: str,
        conclusion: str | None = None,
        error: ProviderError | None = None,
        patch: PatchEnvelope | None = None,
    ) -> NormalizedResult:
        return NormalizedResult(
            result_id=f"result-{request.run_id}",
            task_id=request.task_id,
            run_id=request.run_id,
            base_revision=0,
            outcome=outcome,
            summary=summary,
            conclusion=conclusion,
            error=error,
            patch=patch,
        )

    @classmethod
    def _failure(
        cls,
        request: ProviderRequest,
        code: ProviderErrorCode,
        message: str,
        *,
        retryable: bool = False,
    ) -> NormalizedResult:
        return cls._result(
            request,
            outcome=ProviderOutcome.FAILED,
            summary=message,
            error=ProviderError(code=code, message=message, retryable=retryable),
        )
