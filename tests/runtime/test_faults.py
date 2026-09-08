from __future__ import annotations

from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, TaskStatus
from sora.providers.mock import FaultMode

from .helpers import make_runtime, wait_for_status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fault", "code"),
    [
        (FaultMode.FAILURE, ProviderErrorCode.INTERNAL),
        (FaultMode.RATE_LIMIT, ProviderErrorCode.RATE_LIMITED),
        (FaultMode.MALFORMED_RESULT, ProviderErrorCode.MALFORMED_RESULT),
        (FaultMode.DISCONNECT, ProviderErrorCode.UNAVAILABLE),
        (FaultMode.UNAVAILABLE, ProviderErrorCode.UNAVAILABLE),
        (FaultMode.UNCERTAIN_LAUNCH, ProviderErrorCode.UNCERTAIN_LAUNCH),
    ],
)
async def test_faults_reach_truthful_terminal_state_without_effect_replay(
    tmp_path: Path,
    fault: FaultMode,
    code: ProviderErrorCode,
) -> None:
    runtime, provider = make_runtime(tmp_path, fault=fault)
    await runtime.start()
    receipt = await runtime.submit_task(f"Exercise {fault.value}.")
    report = await runtime.wait_for_task(receipt.task.task_id)
    counts = await runtime.repository.counts()
    await runtime.close()

    assert report.status is TaskStatus.FAILED
    assert not report.completed
    assert report.result is not None and report.result.error is not None
    assert report.result.error.code is code
    assert "no completion is claimed" in report.message
    assert counts["facts"] == 0
    assert counts["normalized_results"] == 1
    assert provider.start_count == 1


@pytest.mark.asyncio
async def test_timeout_is_bounded_and_truthful(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, delay=0.2, timeout=0.03)
    await runtime.start()
    receipt = await runtime.submit_task("Exceed the configured deadline.")
    report = await runtime.wait_for_task(receipt.task.task_id)
    await runtime.close()

    assert report.status is TaskStatus.FAILED
    assert report.result is not None and report.result.error is not None
    assert report.result.error.code is ProviderErrorCode.TIMED_OUT


@pytest.mark.asyncio
async def test_explicit_retry_is_bounded_and_preserves_attempt_history(tmp_path: Path) -> None:
    runtime, provider = make_runtime(tmp_path, fault=FaultMode.RATE_LIMIT)
    await runtime.start()
    receipt = await runtime.submit_task("Retry a transient failure explicitly.")
    failed = await runtime.wait_for_task(receipt.task.task_id)
    assert failed.status is TaskStatus.FAILED

    provider.fault = FaultMode.NONE
    retried = await runtime.retry(receipt.task.task_id)
    completed = await runtime.wait_for_task(retried.task_id)
    runs = await runtime.runtime_repository.list_runs(retried.task_id)
    await runtime.close()

    assert completed.status is TaskStatus.COMPLETED
    assert [run.attempt for run in runs] == [1, 2]
    assert runs[0].status.value == "failed"
    assert runs[1].status.value == "completed"
    assert provider.start_count == 2

    with pytest.raises(RuntimeError, match="not been started"):
        await runtime.retry(retried.task_id)


@pytest.mark.asyncio
async def test_retry_limit_rejects_an_unbounded_third_attempt(tmp_path: Path) -> None:
    runtime, _ = make_runtime(
        tmp_path,
        fault=FaultMode.FAILURE,
        max_attempts=2,
    )
    await runtime.start()
    receipt = await runtime.submit_task("Fail within a bounded retry policy.")
    await runtime.wait_for_task(receipt.task.task_id)
    await runtime.retry(receipt.task.task_id)
    await runtime.wait_for_task(receipt.task.task_id)

    with pytest.raises(ValueError, match="2-attempt limit"):
        await runtime.retry(receipt.task.task_id)
    runs = await runtime.runtime_repository.list_runs(receipt.task.task_id)
    await runtime.close()

    assert [run.attempt for run in runs] == [1, 2]


@pytest.mark.asyncio
async def test_unsupported_steering_is_typed_and_has_no_fake_success(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, delay=0.1, supports_steer=False)
    await runtime.start()
    receipt = await runtime.submit_task("Remain active for steering.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)

    error = await runtime.steer(receipt.task.task_id, "Change direction.")
    await runtime.wait_for_task(receipt.task.task_id)
    await runtime.close()

    assert error is not None
    assert error.code is ProviderErrorCode.UNSUPPORTED


@pytest.mark.asyncio
async def test_supported_steering_reaches_the_active_run(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, fault=FaultMode.DELAY, delay=0.1)
    await runtime.start()
    receipt = await runtime.submit_task("Remain active for valid steering.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)

    error = await runtime.steer(receipt.task.task_id, "Focus on recovery evidence.")
    report = await runtime.wait_for_task(receipt.task.task_id)
    await runtime.close()

    assert error is None
    assert report.result is not None
    assert report.result.conclusion is not None
    assert "Focus on recovery evidence." in report.result.conclusion


@pytest.mark.asyncio
async def test_cancel_race_retains_late_completion_without_applying_patch(tmp_path: Path) -> None:
    runtime, _ = make_runtime(tmp_path, fault=FaultMode.CANCEL_RACE, delay=0.1)
    await runtime.start()
    receipt = await runtime.submit_task("Complete concurrently with cancellation.")
    await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)
    assert await runtime.cancel(receipt.task.task_id)

    report = await runtime.wait_for_task(receipt.task.task_id)
    counts = await runtime.repository.counts()
    await runtime.close()

    assert report.status is TaskStatus.CANCELLED
    assert report.result is not None
    assert report.result.outcome.value == "completed"
    assert counts["facts"] == 0
