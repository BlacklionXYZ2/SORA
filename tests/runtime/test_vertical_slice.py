from __future__ import annotations

import json
from pathlib import Path

import pytest

from sora.contracts.models import EventEnvelope, TaskStatus

from .helpers import make_runtime


@pytest.mark.asyncio
async def test_message_task_run_result_patch_restart_vertical_slice(tmp_path: Path) -> None:
    runtime, provider = make_runtime(tmp_path)
    await runtime.start()
    first = await runtime.submit_task(
        "Analyze the deterministic fixture.",
        idempotency_key="submission-once",
    )
    await runtime.dialogue("Do not let this later response replace the task acknowledgement.")
    duplicate = await runtime.submit_task(
        "Analyze the deterministic fixture.",
        idempotency_key="submission-once",
    )

    report = await runtime.wait_for_task(first.task.task_id)
    traces = await runtime.runtime_repository.traces(first.task.task_id)
    await runtime.close()

    assert first.created
    assert not duplicate.created
    assert duplicate.task.task_id == first.task.task_id
    assert duplicate.acknowledgement_id == first.acknowledgement_id
    assert duplicate.acknowledgement == first.acknowledgement
    assert provider.start_count == 1
    assert report.status is TaskStatus.COMPLETED
    assert report.completed
    assert report.result is not None and report.result.patch is not None
    assert {trace.phase for trace in traces} >= {
        "task.submitted",
        "task.duplicate",
        "context.compiled",
        "provider.launching",
        "result.accepted",
        "patch.applied",
        "run.finished",
    }
    assert all(trace.task_id == first.task.task_id for trace in traces)
    assert await runtime.runtime_repository.lease_count() == 0

    reopened, replacement_provider = make_runtime(tmp_path)
    reconciled = await reopened.start()
    restored = await reopened.report(first.task.task_id)
    counts = await reopened.repository.counts()
    await reopened.close()

    assert reconciled == []
    assert restored.status is TaskStatus.COMPLETED
    assert replacement_provider.start_count == 0
    assert counts["facts"] == 1
    assert counts["normalized_results"] == 1


@pytest.mark.asyncio
async def test_outbox_marks_only_successfully_delivered_events(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path)
    await runtime.start()
    receipt = await runtime.submit_task("Produce durable events.")
    await runtime.wait_for_task(receipt.task.task_id)
    before = await runtime.runtime_repository.pending_outbox()

    async def fail_first(_event: EventEnvelope) -> None:
        raise RuntimeError("client disconnected")

    with pytest.raises(RuntimeError, match="disconnected"):
        await runtime.dispatch_outbox(fail_first)
    assert len(await runtime.runtime_repository.pending_outbox()) == len(before)

    delivered: list[str] = []

    async def consume(event: EventEnvelope) -> None:
        delivered.append(event.event_id)

    count = await runtime.dispatch_outbox(consume)
    await runtime.close()

    assert count == len(before)
    assert delivered
    assert await runtime.runtime_repository.pending_outbox() == []


@pytest.mark.asyncio
async def test_trace_fields_are_redacted_and_manifest_contains_no_context_text(
    tmp_path: Path,
) -> None:
    secret = "sk-runtime-secret-123456"
    runtime, _ = make_runtime(tmp_path, secrets=(secret,))
    await runtime.start()
    receipt = await runtime.submit_task(f"Analyze this without logging {secret}.")
    await runtime.wait_for_task(receipt.task.task_id)
    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    await runtime.close()

    rendered = json.dumps([trace.model_dump(mode="json") for trace in traces])
    assert secret not in rendered
    context_trace = next(trace for trace in traces if trace.phase == "context.compiled")
    assert "sources" in context_trace.fields
    assert "Analyze this" not in rendered
