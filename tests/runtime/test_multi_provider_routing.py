from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    PatchEnvelope,
    PresentationMode,
    ProposedFact,
    ProposeFactOperation,
    ProviderCapabilities,
    ProviderError,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderRequest,
    TaskStatus,
)
from sora.providers.base import ProviderLaunchError, ReasoningProvider
from sora.providers.mock import DeterministicProvider
from sora.routing.router import RoutingEngine
from sora.runtime.service import RuntimeConfig, SoraRuntime


class MockSpecialistProvider:
    """Mock specialist provider for routing and fallback tests."""

    def __init__(
        self,
        name: str,
        *,
        fail_unavailable: bool = False,
        can_steer: bool = False,
        delay_seconds: float = 0.0,
    ) -> None:
        self.name = name
        self.fail_unavailable = fail_unavailable
        self.can_steer = can_steer
        self.delay_seconds = delay_seconds
        self.started_runs: list[str] = []
        self.steered_runs: list[tuple[str, str]] = []
        self._requests: dict[str, ProviderRequest] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            sessions=True,
            resume=True,
            events=False,
            steer=self.can_steer,
            cancel=True,
            tool_restrictions=False,
            display_name=self.name.capitalize(),
        )

    async def start(self, request: ProviderRequest) -> str:
        if self.fail_unavailable:
            raise ProviderLaunchError(
                ProviderErrorCode.UNAVAILABLE,
                f"{self.name} is currently offline",
            )
        self.started_runs.append(request.run_id)
        self._requests[request.run_id] = request
        return request.run_id

    async def result(self, run_id: str) -> NormalizedResult:
        if self.delay_seconds > 0:
            await asyncio.sleep(self.delay_seconds)
        req = self._requests.get(run_id)
        task_id = req.task_id if req else "task-1"
        fact_op = ProposeFactOperation(
            operation="propose_fact",
            operation_id=f"fact-{run_id}",
            fact=ProposedFact(
                content=f"Result from {self.name}",
                epistemic_status="inference",
                confidence=0.9,
            ),
        )
        scope = (
            f"{req.owner_id}/{req.project_id}"
            if (req and req.project_id)
            else (req.owner_id if req else "owner-local")
        )
        patch = PatchEnvelope(
            patch_id=f"patch-{run_id}",
            source_run_id=run_id,
            base_revision=0,
            scope=scope,
            provenance=f"specialist-{self.name}",
            idempotency_key=f"patch-key-{run_id}",
            operations=(fact_op,),
        )
        return NormalizedResult(
            result_id=f"res-{run_id}",
            task_id=task_id,
            run_id=run_id,
            base_revision=0,
            outcome=ProviderOutcome.COMPLETED,
            summary=f"Analysis by {self.name}",
            conclusion=f"Completed research with {self.name}",
            facts=(f"Result from {self.name}",),
            patch=patch,
        )

    async def steer(self, run_id: str, instruction: str) -> None:
        if not self.can_steer:
            raise NotImplementedError("steering unsupported")
        self.steered_runs.append((run_id, instruction))

    async def cancel(self, run_id: str) -> None:
        pass

    async def status(self, run_id: str) -> str:
        return "completed"

    async def session_id(self, run_id: str) -> str | None:
        return f"session-{run_id}"

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        return await self.start(request)

    async def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        if False:
            yield EventEnvelope.model_construct()


IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def make_runtime(
    tmp_path: Path,
    providers: dict[str, ReasoningProvider],
) -> SoraRuntime:
    config = RuntimeConfig(
        root=tmp_path,
        identity_root=IDENTITY_ROOT,
        task_timeout_seconds=5.0,
        worker_count=1,
    )
    routing_engine = RoutingEngine(
        registered_providers=set(providers.keys()),
    )
    return SoraRuntime(
        config=config,
        providers=providers,
        routing_engine=routing_engine,
    )


@pytest.mark.asyncio
async def test_runtime_auto_routes_research_to_antigravity(tmp_path: Path) -> None:
    mock_ag = MockSpecialistProvider("antigravity")
    mock_det = DeterministicProvider()
    runtime = make_runtime(tmp_path, {"antigravity": mock_ag, "deterministic": mock_det})
    await runtime.start()

    receipt = await runtime.submit_task("Research database lock concurrency")
    report = await runtime.wait_for_task(receipt.task.task_id)

    assert report.status is TaskStatus.COMPLETED
    assert "antigravity" in mock_ag.started_runs[0] or len(mock_ag.started_runs) > 0

    run = await runtime.runtime_repository.get_run(receipt.run.run_id)
    assert run is not None
    assert run.native_session_id == f"session-{receipt.run.run_id}"

    # Verify traces include routing.selected
    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    phases = [t.phase for t in traces]
    assert "routing.selected" in phases
    assert "session.attached" in phases

    selected_trace = next(t for t in traces if t.phase == "routing.selected")
    assert selected_trace.fields.get("selected_provider") == "antigravity"

    # Verify presentation maps to friendly specialist
    assert report.result is not None
    presentation = runtime.present_result(report.result)
    assert presentation.actor_provenance == "Aggie"  # VISION.md name for Antigravity
    assert presentation.mode is PresentationMode.EXPLAIN

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_explicit_override_is_honored(tmp_path: Path) -> None:
    mock_ag = MockSpecialistProvider("antigravity")
    mock_hermes = MockSpecialistProvider("hermes")
    runtime = make_runtime(tmp_path, {"antigravity": mock_ag, "hermes": mock_hermes})
    await runtime.start()

    receipt = await runtime.submit_task(
        "Research something",
        explicit_provider="hermes",
    )
    report = await runtime.wait_for_task(receipt.task.task_id)

    assert report.status is TaskStatus.COMPLETED
    assert len(mock_hermes.started_runs) == 1
    assert len(mock_ag.started_runs) == 0

    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    selected_trace = next(t for t in traces if t.phase == "routing.selected")
    assert selected_trace.fields.get("rule_name") == "manual_override"
    assert selected_trace.fields.get("fallback_providers") == []

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_explicit_override_rejects_missing_without_silent_substitution(
    tmp_path: Path,
) -> None:
    mock_det = DeterministicProvider()
    runtime = make_runtime(tmp_path, {"deterministic": mock_det})
    await runtime.start()

    with pytest.raises(ProviderLaunchError) as exc_info:
        await runtime.submit_task("Do task", explicit_provider="missing-provider")
    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE
    assert "silent substitution prohibited" in str(exc_info.value)

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_bounded_auto_fallback_on_unavailable_provider(tmp_path: Path) -> None:
    # Antigravity fails unavailable, should fallback to hermes
    mock_ag_failing = MockSpecialistProvider("antigravity", fail_unavailable=True)
    mock_hermes = MockSpecialistProvider("hermes")
    runtime = make_runtime(
        tmp_path,
        {"antigravity": mock_ag_failing, "hermes": mock_hermes},
    )
    await runtime.start()

    receipt = await runtime.submit_task("Research system performance")
    report = await runtime.wait_for_task(receipt.task.task_id)

    assert report.status is TaskStatus.COMPLETED
    assert len(mock_hermes.started_runs) == 1

    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    phases = [t.phase for t in traces]
    assert "routing.selected" in phases
    assert "routing.fallback" in phases

    fallback_trace = next(t for t in traces if t.phase == "routing.fallback")
    assert fallback_trace.fields.get("original_provider") == "antigravity"
    assert fallback_trace.fields.get("fallback_provider") == "hermes"
    run = await runtime.runtime_repository.get_run(receipt.run.run_id)
    task = await runtime.runtime_repository.get_task(receipt.task.task_id)
    assert run is not None
    assert task is not None
    assert run.provider == "hermes"
    assert task.effective_backend == "hermes"
    assert run.native_session_id == f"session-{receipt.run.run_id}"

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_explicit_failure_does_not_fallback(tmp_path: Path) -> None:
    # When explicitly requested, a failure must NOT silently fallback
    mock_ag_failing = MockSpecialistProvider("antigravity", fail_unavailable=True)
    mock_hermes = MockSpecialistProvider("hermes")
    runtime = make_runtime(
        tmp_path,
        {"antigravity": mock_ag_failing, "hermes": mock_hermes},
    )
    await runtime.start()

    receipt = await runtime.submit_task(
        "Research something",
        explicit_provider="antigravity",
    )
    report = await runtime.wait_for_task(receipt.task.task_id)

    assert report.status is TaskStatus.FAILED
    assert len(mock_hermes.started_runs) == 0

    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    phases = [t.phase for t in traces]
    assert "routing.fallback" not in phases

    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_conversational_steering(tmp_path: Path) -> None:
    mock_hermes = MockSpecialistProvider("hermes", can_steer=True, delay_seconds=0.5)
    mock_ag = MockSpecialistProvider("antigravity", can_steer=False, delay_seconds=0.5)
    runtime = make_runtime(tmp_path, {"hermes": mock_hermes, "antigravity": mock_ag})
    await runtime.start()

    # Submit Hermes task
    receipt_hermes = await runtime.submit_task(
        "Hermes task",
        explicit_provider="hermes",
    )
    await asyncio.sleep(0.05)

    # Conversational steering directed to Hermes
    target_id, message = await runtime.steer_from_conversation(
        "Tell Hermes not to touch the public API"
    )
    assert target_id == receipt_hermes.task.task_id
    assert "Steered task" in message
    assert len(mock_hermes.steered_runs) == 1

    # Conversational steering to non-existent specialist
    target_none, message_none = await runtime.steer_from_conversation("Tell Cody to fix formatting")
    assert target_none is None

    await runtime.wait_for_task(receipt_hermes.task.task_id)
    await runtime.close()


def test_adaptive_presentation_modes() -> None:
    config = RuntimeConfig(root=Path("C:/tmp/test"))
    runtime = SoraRuntime(config=config, provider=DeterministicProvider())

    # Small fix
    small_res = NormalizedResult(
        result_id="res-small",
        task_id="task-1",
        run_id="run-1",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="Fixed a typo",
        conclusion="Typo fixed",
        files_changed=("file1.txt",),
    )
    pres_small = runtime.present_result(small_res)
    assert pres_small.mode is PresentationMode.BRIEF
    assert pres_small.significance == "medium"

    # Significant change
    sig_res = NormalizedResult(
        result_id="res-sig",
        task_id="task-2",
        run_id="run-2",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="Refactored module",
        conclusion="Refactored 3 files",
        files_changed=("a.py", "b.py", "c.py"),
    )
    pres_sig = runtime.present_result(sig_res)
    assert pres_sig.mode is PresentationMode.EXPLAIN
    assert pres_sig.significance == "high"

    # Large walkthrough change
    large_res = NormalizedResult(
        result_id="res-large",
        task_id="task-3",
        run_id="run-3",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="Massive overhaul",
        conclusion="Overhauled 6 files",
        files_changed=("1.py", "2.py", "3.py", "4.py", "5.py", "6.py"),
    )
    pres_large = runtime.present_result(large_res)
    assert pres_large.mode is PresentationMode.WALKTHROUGH
    assert pres_large.significance == "high"

    # Failure
    fail_res = NormalizedResult(
        result_id="res-fail",
        task_id="task-4",
        run_id="run-4",
        base_revision=0,
        outcome=ProviderOutcome.FAILED,
        summary="Failed to build",
        conclusion="Compilation error",
        error=ProviderError(code=ProviderErrorCode.INTERNAL, message="Compilation error"),
    )
    pres_fail = runtime.present_result(fail_res)
    assert pres_fail.mode is PresentationMode.EXPLAIN
    assert pres_fail.attention_required is True
