"""Injected ticks and actual canonical task admission; no owner/provider/native acceptance."""

from __future__ import annotations

import asyncio
import json
import threading
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import pytest
import pytest_asyncio

from sora.contracts.automation import AutomationOccurrence
from sora.contracts.automation_api import AutomationChange, AutomationCreate, AutomationRunNow
from sora.contracts.models import AgentRunRecord, RunStatus, TaskRecord, TaskStatus
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.automation_worker import AutomationWorker
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError

NOW = datetime(2026, 10, 4, 12, tzinfo=UTC)
IDENTITY = Path(__file__).resolve().parents[2] / "identity"


class Clock:
    value = NOW

    def __call__(self) -> datetime:
        return self.value


type Fixture = tuple[SoraRuntime, AutomationWorker, Clock, DeterministicProvider]


@pytest_asyncio.fixture
async def fixture(tmp_path: Path) -> AsyncIterator[Fixture]:
    provider = DeterministicProvider()
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY), provider=provider)
    await runtime.start()
    await runtime.automation_worker.stop()
    clock = Clock()
    worker = AutomationWorker(runtime, clock=clock, batch_size=2)
    worker.started_at = NOW
    runtime.automation_worker = worker
    try:
        yield runtime, worker, clock, provider
    finally:
        await runtime.close()


async def create(
    worker: AutomationWorker,
    *,
    missed: str = "skip",
    due: datetime | None = None,
    provider: str = "deterministic-mock",
    state: str = "active",
    name: str = "Fixture",
) -> str:
    ack = await worker.store.mutate(
        AutomationCreate.model_validate(
            {
                "instance_id": worker.store.instance,
                "request_id": str(uuid.uuid4()),
                "state": state,
                "spec": {
                    "name": name,
                    "trigger": {
                        "kind": "interval",
                        "timezone": "UTC",
                        "anchor_at": (due or NOW + timedelta(seconds=1)),
                        "seconds": 60,
                    },
                    "behavior": {
                        "intent": "Only reason about this PRIVATE-AUTOMATION fixture",
                        "provider": provider,
                    },
                    "missed_policy": missed,
                },
            }
        ),
        observed_at=NOW - timedelta(days=1),
    )
    return ack.definition.automation_id


async def occurrences(
    worker: AutomationWorker, identifier: str
) -> tuple[AutomationOccurrence, ...]:
    return (
        await worker.runtime.repository.database.read(
            lambda db: worker.store.history_in(db, identifier)
        )
    ).occurrences


async def reserve(worker: AutomationWorker, identifier: str, now: datetime) -> AutomationOccurrence:
    detail = await worker.runtime.repository.database.read(
        lambda db: worker.store.detail_in(db, identifier)
    )
    assert detail.next_slot is not None
    value = await worker.store.reserve_scheduled(
        identifier,
        detail.definition.entity_version,
        detail.next_slot.slot_key,
        now=now,
        recovered=False,
    )
    assert value is not None and value.status == "reserved"
    return value


@pytest.mark.asyncio
async def test_tick_admits_one_actual_task_then_records_canonical_completion(
    fixture: Fixture,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    await worker.tick()
    assert await runtime.runtime_repository.list_tasks() == []
    clock.value += timedelta(seconds=1)
    await asyncio.gather(worker.tick(), worker.tick(), worker.tick())
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    tasks = await runtime.runtime_repository.list_tasks()
    assert len(tasks) == 1 and provider.start_count == 1
    for _ in range(3):
        await worker.tick()
    values = await occurrences(worker, identifier)
    assert len(values) == 1 and values[0].status == "completed"
    assert (values[0].task_id, values[0].run_id) == (tasks[0].task_id, tasks[0].active_run_id)
    events = await runtime.repository.database.read(
        lambda db: [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM events "
                "WHERE json_extract(payload,'$.event_type') LIKE 'automation.%'"
            )
        ]
    )
    assert len(events) >= 4 and "PRIVATE-AUTOMATION" not in json.dumps(events)
    detail = await runtime.repository.database.read(
        lambda db: worker.store.detail_in(db, identifier)
    )
    assert detail.next_slot is not None
    assert detail.next_slot.decision_at == NOW + timedelta(seconds=61)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["pause", "edit", "delete"])
async def test_reserved_old_version_cannot_admit_after_owner_change(
    fixture: Fixture, action: Literal["pause", "edit", "delete"]
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    detail = await runtime.repository.database.read(
        lambda db: worker.store.detail_in(db, identifier)
    )
    fields: dict[str, Any] = {}
    if action == "edit":
        fields["spec"] = detail.definition.spec.model_copy(update={"name": "Changed"})
    await worker.store.mutate(
        AutomationChange(
            instance_id=uuid.UUID(worker.store.instance),
            request_id=uuid.uuid4(),
            expected_version=1,
            action=action,
            **fields,
        ),
        identifier,
        observed_at=clock.value,
    )
    await worker.dispatch(pending)
    assert (await occurrences(worker, identifier))[0].status == "blocked"
    assert await runtime.runtime_repository.list_tasks() == [] and provider.start_count == 0


@pytest.mark.asyncio
async def test_admission_event_failure_rolls_back_task_run_submission_and_link(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    original = runtime.repository._append_event

    def fail(*args: Any, **kwargs: Any) -> str:
        if args[3] == "automation.occurrence.admitted":
            raise RuntimeError("PRIVATE-PATH injected failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.repository, "_append_event", fail)
    await worker.dispatch(pending)
    assert await runtime.runtime_repository.list_tasks() == [] and provider.start_count == 0
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
        )
        == 0
    )
    value = (await occurrences(worker, identifier))[0]
    assert (
        value.status == "blocked"
        and value.task_id is None
        and value.reason == "admission_unavailable"
    )


@pytest.mark.asyncio
async def test_committed_admission_then_post_commit_failure_is_not_replayed(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)

    original_trace = runtime.runtime_repository.record_trace

    async def fail(**kwargs: Any) -> Any:
        if kwargs.get("phase") == "routing.selected":
            raise RuntimeError("PRIVATE postcommit trace failure")
        return await original_trace(**kwargs)

    monkeypatch.setattr(runtime.runtime_repository, "record_trace", fail)
    await worker.dispatch(pending)
    tasks = await runtime.runtime_repository.list_tasks()
    assert len(tasks) == 1 and (await occurrences(worker, identifier))[0].status == "admitted"
    # The committed task is enqueued even if later trace recording fails.
    monkeypatch.undo()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    replacement = AutomationWorker(runtime, clock=clock)
    replacement.started_at = clock.value + timedelta(seconds=1)
    await replacement.tick()
    assert len(await runtime.runtime_repository.list_tasks()) == 1 and provider.start_count == 1
    assert (await occurrences(worker, identifier))[0].status == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missed,status,count", [("skip", "skipped", 0), ("run_once", "admitted", 1)]
)
async def test_startup_reservations_obey_recovery_policy_without_burst(
    fixture: Fixture,
    missed: str,
    status: str,
    count: int,
) -> None:
    runtime, worker, clock, _ = fixture
    identifier = await create(worker, missed=missed)
    clock.value += timedelta(seconds=1)
    await reserve(worker, identifier, clock.value)
    clock.value += timedelta(seconds=10)
    replacement = AutomationWorker(runtime, clock=clock)
    replacement.started_at = clock.value
    await replacement.tick()
    assert (await occurrences(worker, identifier))[0].status == status
    assert len(await runtime.runtime_repository.list_tasks()) == count


@pytest.mark.asyncio
async def test_pending_exact_submission_is_linked_not_resubmitted(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    key = await runtime.repository.database.read(
        lambda db: worker.admission.key_in(db, pending.occurrence_id)
    )
    # Crash-boundary fixture: a legacy submission committed without occurrence linkage.
    with owner_local_scope():
        receipt = await runtime.submit_task(
            pending.behavior.intent,
            idempotency_key=key,
            explicit_provider=pending.behavior.provider,
        )
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    replacement = AutomationWorker(runtime, clock=clock)
    replacement.started_at = clock.value + timedelta(seconds=1)
    await replacement.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "completed" and value.task_id == receipt.task.task_id
    assert provider.start_count == 1 and len(await runtime.runtime_repository.list_tasks()) == 1


@pytest.mark.asyncio
async def test_uncertain_run_blocks_overlap_without_automatic_retry(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    provider.fault = FaultMode.UNCERTAIN_LAUNCH
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    await worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    for _ in range(3):
        await worker.tick()
    old = (await occurrences(worker, identifier))[0]
    assert old.status == "unknown"
    clock.value += timedelta(seconds=60)
    for _ in range(3):
        await worker.tick()
    values = await occurrences(worker, identifier)
    assert len(values) == 2 and values[0].reason == "skip_overlap"
    assert len(await runtime.runtime_repository.list_tasks()) == 1


@pytest.mark.asyncio
async def test_repeated_cleanup_of_cancelled_worker_is_safe(fixture: Fixture) -> None:
    _, worker, _, _ = fixture
    worker.start()
    task = worker.task
    assert task is not None
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await worker.stop()
    await worker.stop()
    assert worker.state == "stopped"


@pytest.mark.asyncio
async def test_reserved_clock_rollback_waits_and_live_missed_slot_is_skipped(
    fixture: Fixture,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    clock.value -= timedelta(seconds=5)
    await worker.tick()
    assert (await occurrences(worker, identifier))[0].status == "reserved"
    assert provider.start_count == 0
    # Still the same Core: a long admission gap uses the defined missed-run policy too.
    clock.value = pending.slot.decision_at + timedelta(seconds=10)
    for _ in range(3):
        await worker.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "skipped" and value.reason == "skip_missed"
    assert await runtime.runtime_repository.list_tasks() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds,count", [(10, 1), (301, 0)])
async def test_manual_request_actual_reopen_admits_once_or_expires(
    fixture: Fixture,
    seconds: int,
    count: int,
) -> None:
    runtime, worker, clock, _ = fixture
    identifier = await create(worker, state="paused")
    worker.store.scheduler_state = lambda: "running"  # Injected availability, not a native claim.
    body = AutomationRunNow(
        instance_id=uuid.UUID(worker.store.instance), request_id=uuid.uuid4(), expected_version=1
    )
    ack = await worker.store.run_now(body, identifier, observed_at=clock.value)
    assert ack.occurrence is not None and ack.occurrence.status == "reserved"
    await runtime.close()
    clock.value += timedelta(seconds=seconds)
    provider = DeterministicProvider()
    reopened = SoraRuntime(runtime.config, provider=provider)
    reopened.automation_worker = AutomationWorker(reopened, clock=clock)
    try:
        await reopened.start()
        await reopened.automation_worker.tick()
        await asyncio.wait_for(reopened._queue.join(), timeout=3)
        await reopened.automation_worker.tick()
        rows = await occurrences(reopened.automation_worker, identifier)
        assert len(rows) == 1 and rows[0].status == ("completed" if count else "blocked")
        if not count:
            assert rows[0].reason == "manual_request_expired"
        assert (
            len(await reopened.runtime_repository.list_tasks()) == count
            and provider.start_count == count
        )
        current = reopened.automation_worker.store
        replay = await current.run_now(
            body.model_copy(update={"instance_id": uuid.UUID(current.instance)}), identifier
        )
        assert replay.replayed and replay.occurrence == ack.occurrence
        assert replay.committed_instance_id == body.instance_id
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_manual_def_edit_and_clock_rollback_do_not_admit_early(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker, state="paused")
    worker.store.scheduler_state = lambda: "running"
    ack = await worker.store.run_now(
        AutomationRunNow(
            instance_id=uuid.UUID(worker.store.instance),
            request_id=uuid.uuid4(),
            expected_version=1,
        ),
        identifier,
        observed_at=clock.value,
    )
    assert ack.occurrence is not None
    clock.value -= timedelta(seconds=5)
    await worker.tick()
    assert (await occurrences(worker, identifier))[
        0
    ].status == "reserved" and provider.start_count == 0
    await worker.store.mutate(
        AutomationChange(
            instance_id=uuid.UUID(worker.store.instance),
            request_id=uuid.uuid4(),
            expected_version=1,
            action="delete",
        ),
        identifier,
        observed_at=NOW,
    )
    clock.value = NOW
    for _ in range(3):
        await worker.tick()
    assert (await occurrences(worker, identifier))[0].status == "blocked"
    assert await runtime.runtime_repository.list_tasks() == []


@pytest.mark.asyncio
async def test_missing_provider_blocks_and_fence_prevents_admission(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker, provider="not-installed")
    clock.value += timedelta(seconds=1)
    await worker.tick()
    assert (await occurrences(worker, identifier))[0].status == "blocked"
    second = await create(worker)
    pending = await reserve(worker, second, clock.value)
    worker.fence()
    await worker.dispatch(pending)
    await worker.tick()
    assert (await occurrences(worker, second))[0].status == "reserved"
    assert await runtime.runtime_repository.list_tasks() == [] and provider.start_count == 0


@pytest.mark.asyncio
async def test_bad_record_and_scanned_batches_do_not_starve_later_definitions(
    fixture: Fixture,
) -> None:
    runtime, worker, clock, provider = fixture
    identifiers = [await create(worker, name=str(index)) for index in range(5)]
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE automation_definitions SET payload='PRIVATE invalid JSON' "
            "WHERE automation_id=?",
            (identifiers[0],),
        )
    )
    clock.value += timedelta(seconds=1)
    await worker.tick()
    assert worker.degraded and len(await runtime.runtime_repository.list_tasks()) == 1
    await worker.tick()
    assert len(await runtime.runtime_repository.list_tasks()) == 3
    await worker.tick()
    assert len(await runtime.runtime_repository.list_tasks()) == 4
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    assert provider.start_count == 4


@pytest.mark.asyncio
async def test_start_stop_is_single_owned_worker_with_no_ticks_after_fence(
    fixture: Fixture,
) -> None:
    _, worker, clock, _ = fixture
    identifier = await create(worker)
    worker.start()
    first = worker.task
    worker.start()
    assert worker.task is first and worker.state == "running"
    await worker.stop()
    assert first is not None and first.done() and str(worker.state) == "stopped"
    clock.value += timedelta(seconds=1)
    await worker.tick()
    assert await occurrences(worker, identifier) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["pause", "stop", "policy"])
async def test_admission_rechecks_after_awaited_provider_metadata(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    change: str,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    entered, release = asyncio.Event(), asyncio.Event()
    original = provider.capabilities

    async def paused_caps() -> Any:
        entered.set()
        await release.wait()
        return await original()

    monkeypatch.setattr(provider, "capabilities", paused_caps)
    dispatch = asyncio.create_task(worker.dispatch(pending))
    await asyncio.wait_for(entered.wait(), timeout=1)
    if change == "pause":
        await worker.store.mutate(
            AutomationChange(
                instance_id=uuid.UUID(worker.store.instance),
                request_id=uuid.uuid4(),
                expected_version=1,
                action="pause",
            ),
            identifier,
            observed_at=clock.value,
        )
    elif change == "stop":
        worker.fence()
    else:

        def disabled(provider_name: str) -> None:
            raise OperationAuthorizationError("PRIVATE disabled after metadata")

        monkeypatch.setattr(worker, "_check_admission", disabled)
    release.set()
    await asyncio.wait_for(dispatch, timeout=1)
    assert await runtime.runtime_repository.list_tasks() == [] and provider.start_count == 0
    value = (await occurrences(worker, identifier))[0]
    assert value.status == ("reserved" if change == "stop" else "blocked")


@pytest.mark.asyncio
async def test_owner_pause_does_not_cancel_an_already_admitted_task(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    provider.fault, provider.delay_seconds = FaultMode.DELAY, 0.05
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    await worker.tick()
    task = (await runtime.runtime_repository.list_tasks())[0]
    await worker.store.mutate(
        AutomationChange(
            instance_id=uuid.UUID(worker.store.instance),
            request_id=uuid.uuid4(),
            expected_version=1,
            action="pause",
        ),
        identifier,
        observed_at=clock.value,
    )
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    for _ in range(3):
        await worker.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "completed" and value.task_id == task.task_id
    clock.value += timedelta(hours=1)
    await worker.tick()
    assert len(await runtime.runtime_repository.list_tasks()) == 1


@pytest.mark.asyncio
async def test_status_alone_cannot_fabricate_completion(fixture: Fixture) -> None:
    runtime, worker, clock, _ = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    await worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    await runtime.repository.database.write(lambda db: db.execute("DELETE FROM normalized_results"))
    for _ in range(3):
        await worker.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "unknown" and value.reason == "completion_evidence_missing"


@pytest.mark.asyncio
async def test_original_run_link_is_not_rewritten_to_an_owner_retry(fixture: Fixture) -> None:
    runtime, worker, clock, _ = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    await worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    original = (await occurrences(worker, identifier))[0]
    assert original.run_id is not None and original.task_id is not None

    def replaced(db: Any) -> None:
        row = db.execute(
            "SELECT payload FROM tasks WHERE task_id=?", (original.task_id,)
        ).fetchone()
        task = TaskRecord.model_validate_json(row[0]).model_copy(
            update={
                "active_run_id": "run-owner-retry",
                "status": TaskStatus.QUEUED,
                "result_ref": None,
            }
        )
        old_run = AgentRunRecord.model_validate_json(
            db.execute(
                "SELECT payload FROM agent_runs WHERE run_id=?",
                (original.run_id,),
            ).fetchone()[0]
        )
        retried = old_run.model_copy(
            update={
                "run_id": "run-owner-retry",
                "attempt": 2,
                "status": RunStatus.PENDING,
                "finished_at": None,
                "started_at": None,
                "outcome": None,
            }
        )
        db.execute(
            "INSERT INTO agent_runs(run_id,task_id,status,payload) VALUES (?,?,?,?)",
            (retried.run_id, task.task_id, retried.status.value, retried.model_dump_json()),
        )
        db.execute(
            "UPDATE tasks SET status=?,payload=? WHERE task_id=?",
            (task.status.value, task.model_dump_json(), task.task_id),
        )

    await runtime.repository.database.write(replaced)
    for _ in range(3):
        await worker.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "unknown" and value.run_id == original.run_id


@pytest.mark.asyncio
async def test_provider_failure_is_inspectable_without_an_automatic_retry(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    provider.fault = FaultMode.FAILURE
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    await worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    for _ in range(3):
        await worker.tick()
    value = (await occurrences(worker, identifier))[0]
    assert value.status == "failed" and value.reason == "canonical_run_failed"
    assert provider.start_count == 1


@pytest.mark.asyncio
async def test_old_due_definition_skip_and_bounded_run_once(fixture: Fixture) -> None:
    runtime, worker, clock, provider = fixture
    skipped = await create(worker, due=NOW - timedelta(seconds=20))
    catchup = await create(worker, missed="run_once", due=NOW - timedelta(seconds=20))
    await worker.tick()
    assert (await occurrences(worker, skipped))[0].reason == "skip_missed"
    assert (await occurrences(worker, catchup))[0].status == "admitted"
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    assert len(await runtime.runtime_repository.list_tasks()) == 1 and provider.start_count == 1


@pytest.mark.asyncio
async def test_http_worker_availability_and_saved_receipt_are_distinct(fixture: Fixture) -> None:
    from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer

    runtime, worker, _, _ = fixture
    worker.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="automation-worker-test"))
    await server.start()
    client = SoraApiClient(f"http://127.0.0.1:{server.actual_port}", "automation-worker-test")
    try:
        code, page = await client._request_dict("GET", "/api/v1/automations")
        assert code == 200 and page["scheduler_state"] == "running"
        request: dict[str, Any] = {
            "instance_id": server.routes.instance_id,
            "request_id": str(uuid.uuid4()),
            "spec": {
                "name": "Paused HTTP",
                "trigger": {
                    "kind": "daily",
                    "timezone": "UTC",
                    "local_time": "12:00",
                },
                "behavior": {"intent": "Fixture", "provider": "deterministic-mock"},
            },
        }
        code, ack = await client._request_dict("POST", "/api/v1/automations", request)
        assert code == 201 and ack["scheduler_state"] == "running"
        await worker.stop()
        _, detail = await client._request_dict(
            "GET", "/api/v1/automations/" + ack["definition"]["automation_id"]
        )
        assert detail["scheduler_state"] == "stopped"
        _, historical = await client._request_dict(
            "GET", "/api/v1/automation-requests/" + request["request_id"]
        )
        assert historical["scheduler_state"] == "running" and historical["replayed"]
        assert await runtime.runtime_repository.list_tasks() == []
    finally:
        await server.close()


@pytest.mark.asyncio
async def test_actual_owned_loop_admits_and_finishes_a_fixture_task(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    admitted = asyncio.Event()
    original = worker.admission.commit_in

    def record(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        # Commit runs in the SQLite thread; signal the test's event loop safely.
        loop.call_soon_threadsafe(admitted.set)

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(worker.admission, "commit_in", record)
    worker.interval = 0.05
    worker.start()
    clock.value += timedelta(seconds=1)
    await asyncio.wait_for(admitted.wait(), timeout=3)
    # The commit signal can precede queue handoff; await dispatch through the tick lock.
    async with worker._tick_lock:
        pass
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    await worker.admission.reconcile(
        (await occurrences(worker, identifier))[0].occurrence_id,
        now=clock.value,
        started_at=NOW,
    )
    assert (
        provider.start_count == 1
        and (await occurrences(worker, identifier))[0].status == "completed"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missed,count", [("skip", 0), ("run_once", 1)])
async def test_actual_core_reopen_reconciles_persisted_reservation(
    fixture: Fixture,
    missed: str,
    count: int,
) -> None:
    runtime, worker, clock, _ = fixture
    identifier = await create(worker, missed=missed)
    clock.value += timedelta(seconds=1)
    await reserve(worker, identifier, clock.value)
    await runtime.close()
    clock.value += timedelta(seconds=10)
    provider = DeterministicProvider()
    reopened = SoraRuntime(runtime.config, provider=provider)
    reopened.automation_worker = AutomationWorker(reopened, clock=clock)
    try:
        await reopened.start()
        await reopened.automation_worker.tick()
        await asyncio.wait_for(reopened._queue.join(), timeout=3)
        await reopened.automation_worker.tick()
        rows = await occurrences(reopened.automation_worker, identifier)
        assert len(rows) == 1 and rows[0].status == ("completed" if count else "skipped")
        assert len(await reopened.runtime_repository.list_tasks()) == count
        assert provider.start_count == count
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_cancelled_awaiter_settles_atomic_commit_and_queue_handoff(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, worker, clock, provider = fixture
    identifier = await create(worker)
    clock.value += timedelta(seconds=1)
    pending = await reserve(worker, identifier, clock.value)
    entered, release = threading.Event(), threading.Event()
    original = worker.admission.commit_in

    def barrier(*args: Any, **kwargs: Any) -> None:
        entered.set()
        if not release.wait(timeout=2):
            raise RuntimeError("Barrier test timed out")
        original(*args, **kwargs)

    monkeypatch.setattr(worker.admission, "commit_in", barrier)
    dispatch = asyncio.create_task(worker.dispatch(pending))
    try:
        assert await asyncio.to_thread(entered.wait, 1)
        worker.fence()
        dispatch.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await dispatch
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    values = await occurrences(worker, identifier)
    assert len(values) == 1 and values[0].task_id is not None and provider.start_count == 1
    assert len(await runtime.runtime_repository.list_tasks()) == 1
