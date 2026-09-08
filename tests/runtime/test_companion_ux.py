from __future__ import annotations

from pathlib import Path

import pytest

from sora.contracts.models import (
    NormalizedResult,
    PresentationMode,
    ProviderError,
    ProviderErrorCode,
    ProviderOutcome,
    TaskStatus,
)
from sora.providers.mock import FaultMode

from .helpers import make_runtime, wait_for_status


@pytest.mark.asyncio
async def test_dialogue_responsive_during_slow_reasoning_task(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, fault=FaultMode.DELAY, delay=0.25)
    await runtime.start()

    assert runtime.dialogue_status() == "available"
    assert await runtime.active_specialists() == ()

    receipt = await runtime.submit_task("Perform slow reasoning work.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)

    assert await runtime.active_specialists() == ("deterministic-mock",)
    assert runtime.dialogue_status() == "available"

    reply = await runtime.dialogue("How are things going?")
    assert "You said: How are things going?" in reply

    streamed_chunks = [
        chunk async for chunk in runtime.stream_dialogue("Are you still with me?")
    ]
    assert "You said: Are you still with me?" in "".join(streamed_chunks)

    report = await runtime.wait_for_task(receipt.task.task_id)
    assert report.status is TaskStatus.COMPLETED
    assert await runtime.active_specialists() == ()

    await runtime.close()


@pytest.mark.asyncio
async def test_steering_dispatch_records_trace(tmp_path: Path) -> None:
    runtime, _ = make_runtime(
        tmp_path,
        fault=FaultMode.DELAY,
        delay=0.25,
        supports_steer=True,
    )
    await runtime.start()

    receipt = await runtime.submit_task("Initial direction.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)

    instruction = "Steer towards safe alternative."
    err = await runtime.steer(receipt.task.task_id, instruction)
    assert err is None

    report = await runtime.wait_for_task(receipt.task.task_id)
    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    steered = [t for t in traces if t.phase == "task.steered"]

    assert len(steered) == 1
    assert steered[0].fields["instruction_length"] == len(instruction)
    assert report.result is not None
    assert report.result.conclusion is not None
    assert instruction in report.result.conclusion

    await runtime.close()


def test_adaptive_result_presentation_modes(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path)

    result_simple = NormalizedResult(
        result_id="res-1",
        task_id="task-1",
        run_id="run-1",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="Quick patch applied.",
        conclusion="Quick patch applied cleanly.",
        files_changed=("a.txt",),
        commands_run=("pytest",),
    )
    pres_brief = runtime.present_result(result_simple)
    assert pres_brief.mode is PresentationMode.BRIEF
    assert pres_brief.summary == "Quick patch applied."
    assert not pres_brief.attention_required
    assert pres_brief.physical_cues == ("nod",)

    result_complex = NormalizedResult(
        result_id="res-2",
        task_id="task-2",
        run_id="run-2",
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary="Refactor finished.",
        conclusion="Massive refactor finished.",
        files_changed=("a.py", "b.py", "c.py"),
        commands_run=("c1", "c2", "c3"),
    )
    pres_explain = runtime.present_result(result_complex)
    assert pres_explain.mode is PresentationMode.EXPLAIN
    assert pres_explain.summary == "Refactor finished."

    result_failed = NormalizedResult(
        result_id="res-3",
        task_id="task-3",
        run_id="run-3",
        base_revision=0,
        outcome=ProviderOutcome.FAILED,
        summary="Build failed.",
        error=ProviderError(
            code=ProviderErrorCode.INTERNAL,
            message="Syntax error in source",
        ),
    )
    pres_failed = runtime.present_result(result_failed)
    assert pres_failed.mode is PresentationMode.EXPLAIN
    assert pres_failed.summary == "Build failed."
    assert pres_failed.attention_required
    assert pres_failed.physical_cues == ()

    result_cancelled = NormalizedResult(
        result_id="res-4",
        task_id="task-4",
        run_id="run-4",
        base_revision=0,
        outcome=ProviderOutcome.CANCELLED,
        summary="Cancelled by operator.",
    )
    pres_cancelled = runtime.present_result(result_cancelled)
    assert pres_cancelled.mode is PresentationMode.BRIEF
    assert pres_cancelled.summary == "Cancelled by operator."

    pres_silent = runtime.present_result(result_simple, mode=PresentationMode.SILENT)
    assert pres_silent.mode is PresentationMode.SILENT

    pres_walkthrough = runtime.present_result(result_simple, mode=PresentationMode.WALKTHROUGH)
    assert pres_walkthrough.mode is PresentationMode.WALKTHROUGH

