"""Manual owner HTTP requests and canonical task evidence, never live-provider/native proof."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from tests.api.test_memory_browser import Browser
from tests.api.test_memory_browser import browser as browser

from sora.api.protocol import HttpRequest
from sora.contracts.automation_api import AutomationCreate, AutomationRunNow
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.automation_store import AutomationStore
from sora.security.operations import OperationAuthorizationError


async def created(browser: Browser, *, state: str = "paused") -> dict[str, Any]:
    _, server, client = browser
    code, ack = await client._request_dict(
        "POST",
        "/api/v1/automations",
        {
            "instance_id": server.routes.instance_id,
            "request_id": str(uuid.uuid4()),
            "state": state,
            "spec": {
                "name": "Manual fixture",
                "trigger": {
                    "kind": "interval",
                    "timezone": "Europe/London",
                    "anchor_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
                    "seconds": 14400,
                },
                "behavior": {
                    "intent": "PRIVATE manual fixture reasoning",
                    "provider": "deterministic-mock",
                },
            },
        },
    )
    assert code == 201
    return ack


def command(ack: dict[str, Any]) -> dict[str, Any]:
    return {
        "instance_id": ack["instance_id"],
        "request_id": str(uuid.uuid4()),
        "expected_version": ack["definition"]["entity_version"],
    }


def path(ack: dict[str, Any]) -> str:
    return f"/api/v1/automations/{ack['definition']['automation_id']}/run-now"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["active", "paused"])
async def test_manual_runs_saved_behavior_without_shifting_slot_or_version(
    browser: Browser,
    state: str,
) -> None:
    runtime, server, client = browser
    saved = await created(browser, state=state)
    body = command(saved)
    code, receipt = await client._request_dict("POST", path(saved), body)
    assert (
        code == 202
        and receipt["action"] == "run_now"
        and receipt["occurrence"]["origin"] == "manual"
    )
    assert (
        receipt["occurrence"]["status"] == "reserved" and receipt["occurrence"]["task_id"] is None
    )
    assert (
        receipt["next_slot"] == saved["next_slot"] and receipt["definition"] == saved["definition"]
    )
    await runtime.automation_worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    for _ in range(3):
        await runtime.automation_worker.tick()
    _, history = await client._request_dict("GET", path(saved).removesuffix("run-now") + "history")
    assert len(history["occurrences"]) == 1 and history["occurrences"][0]["status"] == "completed"
    tasks = await runtime.runtime_repository.list_tasks()
    assert len(tasks) == 1 and history["occurrences"][0]["task_id"] == tasks[0].task_id
    _, detail = await client._request_dict("GET", path(saved).removesuffix("/run-now"))
    assert detail["definition"] == saved["definition"] and detail["next_slot"] == saved["next_slot"]
    _, historical = await client._request_dict(
        "GET", "/api/v1/automation-requests/" + body["request_id"]
    )
    assert historical["occurrence"] == receipt["occurrence"] and historical["replayed"]
    code, duplicate = await client._request_dict("POST", path(saved), body)
    assert code == 200 and duplicate["event_id"] == receipt["event_id"]
    assert len(await runtime.runtime_repository.list_tasks()) == 1
    events = await runtime.repository.database.read(
        lambda db: [
            json.loads(row[0])
            for row in db.execute(
                "SELECT payload FROM events "
                "WHERE json_extract(payload,'$.event_type') LIKE 'automation.%'"
            )
        ]
    )
    assert len(events) >= 4 and "PRIVATE manual" not in json.dumps(events)
    assert server.routes.instance_id == historical["instance_id"]


@pytest.mark.asyncio
async def test_concurrent_manual_duplicates_and_changed_key_conflict(browser: Browser) -> None:
    runtime, _, client = browser
    saved = await created(browser)
    body = command(saved)
    replies = await asyncio.gather(
        *(client._request_dict("POST", path(saved), body) for _ in range(3))
    )
    assert sorted(code for code, _ in replies) == [200, 200, 202]
    assert len({ack["occurrence"]["occurrence_id"] for _, ack in replies}) == 1
    assert (await client._request_dict("POST", path(saved), {**body, "expected_version": 2}))[
        0
    ] == 409
    await runtime.automation_worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    assert len(await runtime.runtime_repository.list_tasks()) == 1


@pytest.mark.asyncio
async def test_fresh_manual_overlap_is_skipped_even_when_definition_is_paused(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    saved = await created(browser)
    # Stop the loop but use an explicit available-state store to pin the reservation boundary.
    await runtime.automation_worker.stop()
    store = AutomationStore(
        runtime.repository,
        runtime.config.owner_id,
        runtime.config.project_id,
        server.routes.instance_id,
        scheduler_state=lambda: "running",
    )
    first = await store.run_now(
        AutomationRunNow.model_validate(command(saved)), saved["definition"]["automation_id"]
    )
    second = await store.run_now(
        AutomationRunNow.model_validate(command(saved)), saved["definition"]["automation_id"]
    )
    assert first.occurrence is not None and first.occurrence.status == "reserved"
    assert second.occurrence is not None and second.occurrence.status == "skipped"
    assert (
        second.occurrence.reason == "skip_overlap"
        and not await runtime.runtime_repository.list_tasks()
    )
    _, history = await client._request_dict("GET", path(saved).removesuffix("run-now") + "history")
    assert len(history["occurrences"]) == 2


@pytest.mark.asyncio
async def test_unavailable_worker_records_blocked_attempt_not_a_future_run(
    browser: Browser,
) -> None:
    runtime, _, client = browser
    saved = await created(browser)
    await runtime.automation_worker.stop()
    code, receipt = await client._request_dict("POST", path(saved), command(saved))
    assert code == 202 and receipt["scheduler_state"] == "stopped"
    assert receipt["occurrence"]["status"] == "blocked"
    assert receipt["occurrence"]["reason"] == "scheduler_unavailable"
    runtime.automation_worker.start()
    await runtime.automation_worker.tick()
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
async def test_manual_policy_failure_is_visible_without_private_exception_text(
    browser: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _, client = browser
    saved = await created(browser)

    def disabled(provider: str) -> None:
        raise OperationAuthorizationError("PRIVATE-CREDENTIAL error fixture")

    monkeypatch.setattr(runtime.automation_worker, "_check_admission", disabled)
    _, ack = await client._request_dict("POST", path(saved), command(saved))
    await runtime.automation_worker.tick()
    _, history = await client._request_dict("GET", path(saved).removesuffix("run-now") + "history")
    assert history["occurrences"][0]["status"] == "blocked"
    assert history["occurrences"][0]["reason"] == "admission_unavailable"
    assert (
        "PRIVATE-CREDENTIAL" not in json.dumps(history)
        and not await runtime.runtime_repository.list_tasks()
    )
    assert ack["occurrence"]["task_id"] is None


@pytest.mark.asyncio
async def test_manual_epoch_version_scope_closed_body_and_methods(browser: Browser) -> None:
    runtime, server, client = browser
    saved = await created(browser)
    body = command(saved)
    for changes in ({"instance_id": str(uuid.uuid4())}, {"expected_version": 2}):
        assert (await client._request_dict("POST", path(saved), {**body, **changes}))[0] == 409
    for invalid_changes in (
        {"intent": "replace saved task"},
        {"authorized_by": "owner-local"},
        {"expected_version": True},
        {"action": "pause"},
    ):
        assert (await client._request_dict("POST", path(saved), {**body, **invalid_changes}))[
            0
        ] == 400
    assert (await client._request_dict("GET", path(saved)))[0] == 405
    assert (await client._request_dict("POST", path(saved) + "?q=x", body))[0] == 400
    await runtime.repository.register_project("manual-hidden", runtime.config.owner_id)
    hidden = AutomationStore(
        runtime.repository, runtime.config.owner_id, "manual-hidden", server.routes.instance_id
    )
    hidden_saved = await hidden.mutate(
        AutomationCreate.model_validate(
            {
                "instance_id": server.routes.instance_id,
                "request_id": str(uuid.uuid4()),
                "spec": saved["definition"]["spec"],
            }
        )
    )
    hidden_path = "/api/v1/automations/" + hidden_saved.definition.automation_id + "/run-now"
    assert (await client._request_dict("POST", hidden_path, body))[0] == 404
    remote = HttpRequest("POST", path(saved), {}, json.dumps(body).encode())
    assert (
        await server.routes.handle_request(remote, remote_scopes=frozenset({"tasks.submit"}))
    ).status_code == 403
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
async def test_manual_event_failure_rolls_back_occurrence_receipt_and_revision(
    browser: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, _, client = browser
    saved = await created(browser)
    body = command(saved)
    original = runtime.repository._append_event

    def fail(*args: Any, **kwargs: Any) -> str:
        if args[3] == "automation.run_now":
            raise sqlite3.OperationalError("PRIVATE failing outbox")
        return original(*args, **kwargs)

    monkeypatch.setattr(runtime.repository, "_append_event", fail)
    code, error = await client._request_dict("POST", path(saved), body)
    assert code == 503 and "PRIVATE" not in json.dumps(error)
    assert (await client._request_dict("GET", "/api/v1/automation-requests/" + body["request_id"]))[
        0
    ] == 404
    _, history = await client._request_dict("GET", path(saved).removesuffix("run-now") + "history")
    assert (
        history["projection_revision"] == saved["projection_revision"]
        and history["occurrences"] == []
    )


@pytest.mark.asyncio
async def test_mutation_request_key_cannot_be_repurposed_as_manual_run(browser: Browser) -> None:
    _, _, client = browser
    saved = await created(browser)
    body = {**command(saved), "request_id": saved["request_id"]}
    assert (await client._request_dict("POST", path(saved), body))[0] == 409


@pytest.mark.asyncio
async def test_manual_historical_replay_survives_delete_without_resurrection(
    browser: Browser,
) -> None:
    runtime, _, client = browser
    saved = await created(browser)
    await runtime.automation_worker.stop()
    body = command(saved)
    _, first = await client._request_dict("POST", path(saved), body)
    code, deleted = await client._request_dict(
        "POST",
        path(saved).removesuffix("/run-now"),
        {
            **command(saved),
            "action": "delete",
        },
    )
    assert code == 200 and deleted["definition"]["state"] == "deleted"
    code, replayed = await client._request_dict("POST", path(saved), body)
    assert code == 200 and replayed["event_id"] == first["event_id"] and replayed["replayed"]
    assert replayed["occurrence"] == first["occurrence"]
    assert (await client._request_dict("POST", path(saved), command(deleted)))[0] == 404
    runtime.automation_worker.start()
    await runtime.automation_worker.tick()
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
async def test_fresh_manual_run_cannot_bypass_unknown_overlap(browser: Browser) -> None:
    runtime, _, client = browser
    provider = cast(DeterministicProvider, runtime._get_provider("deterministic-mock"))
    provider.fault = FaultMode.UNCERTAIN_LAUNCH
    saved = await created(browser)
    await client._request_dict("POST", path(saved), command(saved))
    await runtime.automation_worker.tick()
    await asyncio.wait_for(runtime._queue.join(), timeout=3)
    for _ in range(3):
        await runtime.automation_worker.tick()
    _, history = await client._request_dict("GET", path(saved).removesuffix("run-now") + "history")
    assert history["occurrences"][0]["status"] == "unknown"
    code, next_attempt = await client._request_dict("POST", path(saved), command(saved))
    assert code == 202 and next_attempt["occurrence"]["status"] == "skipped"
    assert next_attempt["occurrence"]["reason"] == "skip_overlap"
    assert len(await runtime.runtime_repository.list_tasks()) == 1
