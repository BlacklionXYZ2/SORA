"""Actual authenticated HTTP/SQLite storage, never a claim of scheduled task execution."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import pytest
import pytest_asyncio
from tests.api.test_memory_browser import Browser
from tests.api.test_memory_browser import browser as browser
from tests.persistence.helpers import sample_message, sample_run, sample_task

from sora.api.protocol import HttpRequest
from sora.contracts.automation_api import AutomationCreate
from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from sora.runtime.automation_store import AutomationConflict, AutomationStore

NOW = datetime(2026, 10, 4, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def stop_fixture_scheduler(browser: Browser) -> None:
    # Storage/reservation tests inject historical clocks, so deliberately stop timing.
    # Real worker admission and lifecycle have their own connected/component coverage.
    await browser[0].automation_worker.stop()


def command(
    instance: str, *, state: str = "paused", name: str = "Fixture Automation"
) -> dict[str, Any]:
    return {
        "instance_id": instance,
        "request_id": str(uuid.uuid4()),
        "state": state,
        "spec": {
            "name": name,
            "trigger": {
                "kind": "interval",
                "timezone": "UTC",
                "anchor_at": (NOW + timedelta(minutes=1)).isoformat(),
                "seconds": 60,
            },
            "behavior": {
                "intent": "PRIVATE-BEHAVIOR only inspect the selected fixture",
                "provider": "auto",
            },
        },
    }


async def changed(
    browser: Browser, ack: dict[str, Any], action: str, **fields: Any
) -> tuple[int, dict[str, Any]]:
    _, _, client = browser
    return await client._request_dict(
        "POST",
        "/api/v1/automations/" + ack["definition"]["automation_id"],
        {
            "instance_id": ack["instance_id"],
            "request_id": str(uuid.uuid4()),
            "expected_version": ack["definition"]["entity_version"],
            "action": action,
            **fields,
        },
    )


@pytest.mark.asyncio
async def test_http_save_receipt_edit_resume_pause_delete_are_not_execution(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    body = command(server.routes.instance_id)
    code, ack = await client._request_dict("POST", "/api/v1/automations", body)
    assert code == 201 and ack["definition"]["state"] == "paused" and ack["next_slot"] is None
    assert ack["scheduler_state"] == "stopped" and not ack["replayed"]
    identifier = ack["definition"]["automation_id"]
    assert (await client._request_dict("GET", "/api/v1/automations/" + identifier))[0] == 200
    _, repeated = await client._request_dict("POST", "/api/v1/automations", body)
    assert (
        repeated["definition"] == ack["definition"]
        and repeated["event_id"] == ack["event_id"]
        and repeated["replayed"]
    )
    replacement = {**body["spec"], "name": "Renamed fixture"}
    code, ack = await changed(browser, ack, "edit", spec=replacement)
    assert code == 200 and ack["definition"]["entity_version"] == 2
    code, ack = await changed(browser, ack, "resume")
    assert code == 200 and ack["definition"]["state"] == "active" and ack["next_slot"]
    _, paused = await changed(browser, ack, "pause")
    assert paused["definition"]["state"] == "paused" and paused["next_slot"] is None
    _, deleted = await changed(browser, paused, "delete")
    assert deleted["definition"]["state"] == "deleted"
    assert (await client._request_dict("GET", "/api/v1/automations/" + identifier))[0] == 404
    _, page = await client._request_dict("GET", "/api/v1/automations")
    assert page["automations"] == []
    assert (await client._request_dict("GET", "/api/v1/automations/" + identifier + "/history"))[
        0
    ] == 200
    _, receipt = await client._request_dict(
        "GET", "/api/v1/automation-requests/" + body["request_id"]
    )
    assert receipt["definition"]["state"] == "paused" and receipt["replayed"]
    events = await runtime.repository.database.read(
        lambda db: [json.loads(row[0]) for row in db.execute("SELECT payload FROM events")]
    )
    assert "PRIVATE-BEHAVIOR" not in json.dumps(events)
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
async def test_concurrent_duplicates_conflicts_and_stale_epoch_versions(browser: Browser) -> None:
    runtime, server, client = browser
    body = command(server.routes.instance_id)
    results = await asyncio.gather(
        *(client._request_dict("POST", "/api/v1/automations", body) for _ in range(3))
    )
    assert sorted(code for code, _ in results) == [200, 200, 201]
    assert len({result["event_id"] for _, result in results}) == 1
    assert (
        await client._request_dict(
            "POST", "/api/v1/automations", {**body, "spec": {**body["spec"], "name": "Different"}}
        )
    )[0] == 409
    assert (
        await client._request_dict(
            "POST", "/api/v1/automations", {**body, "instance_id": str(uuid.uuid4())}
        )
    )[0] == 409
    ack = results[0][1]
    _, updated = await changed(browser, ack, "edit", spec={**body["spec"], "name": "New version"})
    assert (await changed(browser, ack, "delete"))[0] == 409
    assert (await changed(browser, updated, "pause"))[
        0
    ] == 409  # Already paused; no disguised reschedule.
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute("SELECT COUNT(*) FROM automation_definitions").fetchone()[0]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_owner_project_scope_private_summary_and_signed_paging(browser: Browser) -> None:
    runtime, server, client = browser
    for index in range(4):
        await client._request_dict(
            "POST",
            "/api/v1/automations",
            command(server.routes.instance_id, name=f"Fixture {index}"),
        )
    await runtime.repository.register_project("hidden-project", runtime.config.owner_id)
    hidden = AutomationStore(
        runtime.repository, runtime.config.owner_id, "hidden-project", server.routes.instance_id
    )
    hidden_ack = await hidden.mutate(
        AutomationCreate.model_validate(command(server.routes.instance_id, name="Hidden"))
    )
    hidden_id = hidden_ack.definition.automation_id
    assert (await client._request_dict("GET", "/api/v1/automations/" + hidden_id))[0] == 404
    assert (await client._request_dict("GET", "/api/v1/automations/" + hidden_id + "/history"))[
        0
    ] == 404
    assert (
        await client._request_dict(
            "GET", "/api/v1/automation-requests/" + str(hidden_ack.request_id)
        )
    )[0] == 404
    _, first = await client._request_dict("GET", "/api/v1/automations?limit=2")
    assert (
        len(first["automations"]) == 2
        and first["next_cursor"]
        and "PRIVATE" not in json.dumps(first)
    )
    await client._request_dict(
        "POST", "/api/v1/automations", command(server.routes.instance_id, name="Later")
    )
    cursor = first["next_cursor"]
    _, second = await client._request_dict(
        "GET", "/api/v1/automations?" + urlencode({"limit": 2, "cursor": cursor})
    )
    assert len(second["automations"]) == 2 and second["next_cursor"] is None
    assert not (
        {row["automation_id"] for row in first["automations"]}
        & {row["automation_id"] for row in second["automations"]}
    )
    assert "Later" not in json.dumps(second) and "Hidden" not in json.dumps(first)
    assert (
        await client._request_dict(
            "GET",
            "/api/v1/automations?" + urlencode({"limit": 2, "cursor": cursor, "state": "active"}),
        )
    )[0] == 400
    assert (
        await client._request_dict(
            "GET", "/api/v1/automations?" + urlencode({"limit": 2, "cursor": cursor[:-1] + "!"})
        )
    )[0] == 400
    _, searched = await client._request_dict("GET", "/api/v1/automations?q=fixture%202")
    assert len(searched["automations"]) == 1 and searched["automations"][0]["name"] == "Fixture 2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    ["/api/v1/automations", "/api/v1/automations/unknown", "/api/v1/automation-requests/unknown"],
)
async def test_remote_routes_are_absent_and_wrong_method_rejected(
    browser: Browser, path: str
) -> None:
    _, server, _ = browser
    response = await server.routes.handle_request(
        HttpRequest("GET", path, {}, b""), remote_scopes=frozenset()
    )
    assert response.status_code == 403
    response = await server.routes.handle_request(HttpRequest("DELETE", path, {}, b""))
    assert response.status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix",
    [
        "?limit=0",
        "?limit=51",
        "?limit=x",
        "?state=deleted",
        "?q=x&q=y",
        "?authority=owner",
        "?cursor=invalid",
    ],
)
async def test_bounded_filters_and_bad_cursors_fail_closed(browser: Browser, suffix: str) -> None:
    _, _, client = browser
    assert (await client._request_dict("GET", "/api/v1/automations" + suffix))[0] == 400


@pytest.mark.asyncio
async def test_closed_writes_corruption_and_atomic_event_failure_are_redacted(
    browser: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, server, client = browser
    body = command(server.routes.instance_id)
    assert (
        await client._request_dict(
            "POST", "/api/v1/automations", {**body, "authorized_by": "owner"}
        )
    )[0] == 400
    before = await runtime.repository.revision()

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise sqlite3.OperationalError("PRIVATE database path")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.repository, "_append_event", broken)
        code, value = await client._request_dict("POST", "/api/v1/automations", body)
        assert code == 503 and "PRIVATE" not in json.dumps(value)
    assert await runtime.repository.revision() == before
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute("SELECT COUNT(*) FROM automation_definitions").fetchone()[0]
        )
        == 0
    )
    _, ack = await client._request_dict("POST", "/api/v1/automations", body)
    identifier = ack["definition"]["automation_id"]
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE automation_definitions SET payload='PRIVATE-CORRUPTION' WHERE automation_id=?",
            (identifier,),
        )
    )
    code, value = await client._request_dict("GET", "/api/v1/automations/" + identifier)
    assert code == 503 and "PRIVATE" not in json.dumps(value)


@pytest.mark.asyncio
async def test_restore_receipts_new_epoch_and_original_rows_from_schema11(tmp_path: Path) -> None:
    path = tmp_path / "migration.db"
    old = SQLiteDatabase(path)
    await old.initialize(target_version=11)
    repository = SoraRepository(old)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.register_conversation("conversation-001", "owner-local", "project-sora")
    await repository.append_message(sample_message())
    await repository.create_task(sample_task())
    await repository.create_run(sample_run())
    revision = await repository.revision()
    await old.initialize()
    assert await old.schema_version() == 15 and await repository.revision() == revision
    assert await repository.get_task("task-001") == sample_task()
    store = AutomationStore(repository, "owner-local", "project-sora", str(uuid.uuid4()))
    request = AutomationCreate.model_validate(command(store.instance))
    ack = await store.mutate(request, observed_at=NOW)
    reopened = SQLiteDatabase(path)
    await reopened.initialize()
    new = AutomationStore(
        SoraRepository(reopened), "owner-local", "project-sora", str(uuid.uuid4())
    )
    replay = await new.mutate(
        request.model_copy(update={"instance_id": uuid.UUID(new.instance)}), observed_at=NOW
    )
    assert replay.replayed and replay.event_id == ack.event_id
    assert replay.committed_instance_id == uuid.UUID(
        store.instance
    ) and replay.instance_id == uuid.UUID(new.instance)
    assert await reopened.read(lambda db: new.receipt_in(db, request.request_id)) == replay


@pytest.mark.asyncio
async def test_reservation_uniqueness_snapshot_overlap_restart_and_stale_edit(
    browser: Browser,
) -> None:
    runtime, server, _ = browser
    store = server.routes.automations
    request = AutomationCreate.model_validate(command(store.instance, state="active"))
    ack = await store.mutate(request, observed_at=NOW)
    identifier = ack.definition.automation_id
    slot = ack.next_slot
    assert slot is not None
    before = await runtime.repository.revision()
    assert (
        await store.reserve_scheduled(identifier, 1, slot.slot_key, now=NOW, recovered=False)
        is None
    )
    assert await runtime.repository.revision() == before
    values = await asyncio.gather(
        *(
            store.reserve_scheduled(
                identifier, 1, slot.slot_key, now=slot.decision_at, recovered=False
            )
            for _ in range(3)
        )
    )
    assert values[0] is not None and len({value.occurrence_id for value in values if value}) == 1
    assert (
        values[0].status == "reserved"
        and values[0].task_id is None
        and values[0].behavior == ack.definition.spec.behavior
    )
    assert await runtime.repository.revision() == before + 1
    restarted = AutomationStore(
        runtime.repository, runtime.config.owner_id, runtime.config.project_id, str(uuid.uuid4())
    )
    assert (
        await restarted.reserve_scheduled(
            identifier, 1, slot.slot_key, now=slot.decision_at, recovered=True
        )
        == values[0]
    )
    detail = await runtime.repository.database.read(lambda db: store.detail_in(db, identifier))
    next_due = detail.next_slot
    assert next_due is not None
    overlap = await store.reserve_scheduled(
        identifier, 1, next_due.slot_key, now=next_due.decision_at, recovered=False
    )
    assert overlap is not None and overlap.status == "skipped" and overlap.reason == "skip_overlap"
    changed_spec = {**request.spec.model_dump(), "name": "Only renamed"}
    current = await runtime.repository.database.read(lambda db: store.detail_in(db, identifier))
    from sora.contracts.automation_api import AutomationChange

    edited = await store.mutate(
        AutomationChange.model_validate(
            {
                "instance_id": store.instance,
                "request_id": str(uuid.uuid4()),
                "expected_version": 1,
                "action": "edit",
                "spec": changed_spec,
            }
        ),
        identifier,
        observed_at=NOW,
    )
    assert edited.next_slot == current.next_slot
    with pytest.raises(AutomationConflict, match="VERSION_STATE"):
        await store.reserve_scheduled(
            identifier, 1, slot.slot_key, now=slot.decision_at, recovered=False
        )
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "policy,status,reason", [("skip", "skipped", "skip_missed"), ("run_once", "reserved", None)]
)
async def test_recovery_advances_interval_without_backlog_burst(
    browser: Browser,
    policy: str,
    status: str,
    reason: str | None,
) -> None:
    runtime, server, _ = browser
    body = command(server.routes.instance_id, state="active")
    body["spec"]["missed_policy"] = policy
    store = server.routes.automations
    ack = await store.mutate(AutomationCreate.model_validate(body), observed_at=NOW)
    assert ack.next_slot is not None
    now = ack.next_slot.decision_at + timedelta(seconds=125)
    value = await store.reserve_scheduled(
        ack.definition.automation_id, 1, ack.next_slot.slot_key, now=now, recovered=True
    )
    assert value is not None and value.status == status and value.reason == reason
    detail = await runtime.repository.database.read(
        lambda db: store.detail_in(db, ack.definition.automation_id)
    )
    assert detail.next_slot is not None and detail.next_slot.decision_at > now
    history = await runtime.repository.database.read(
        lambda db: store.history_in(db, ack.definition.automation_id)
    )
    assert len(history.occurrences) == 1


@pytest.mark.asyncio
async def test_history_pages_reservations_without_replay_or_fake_task_evidence(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    store = server.routes.automations
    ack = await store.mutate(
        AutomationCreate.model_validate(command(store.instance, state="active")), observed_at=NOW
    )
    identifier = ack.definition.automation_id
    for _ in range(8):
        detail = await runtime.repository.database.read(lambda db: store.detail_in(db, identifier))
        slot = detail.next_slot
        assert slot is not None
        await store.reserve_scheduled(
            identifier, 1, slot.slot_key, now=slot.decision_at, recovered=False
        )
    path = "/api/v1/automations/" + identifier + "/history"
    seen: set[str] = set()
    cursor = None
    for _ in range(3):
        code, page = await client._request_dict(
            "GET", path + "?" + urlencode({"limit": 3, **({"cursor": cursor} if cursor else {})})
        )
        assert code == 200 and len(page["occurrences"]) <= 3
        ids = {row["occurrence_id"] for row in page["occurrences"]}
        assert not seen & ids
        seen.update(ids)
        assert all(
            row["task_id"] is None and row["status"] in {"reserved", "skipped"}
            for row in page["occurrences"]
        )
        cursor = page["next_cursor"]
    assert len(seen) == 8 and cursor is None
    _, fresh = await client._request_dict("GET", path + "?limit=3")
    invalid = await client._request_dict(
        "GET", path + "?" + urlencode({"limit": 2, "cursor": fresh["next_cursor"]})
    )
    assert invalid[0] == 400
    new = AutomationStore(
        runtime.repository, runtime.config.owner_id, runtime.config.project_id, str(uuid.uuid4())
    )
    with pytest.raises(ValueError, match="cursor"):
        await runtime.repository.database.read(
            lambda db: new.history_in(db, identifier, limit=3, cursor=fresh["next_cursor"])
        )
    assert not await runtime.runtime_repository.list_tasks()


@pytest.mark.asyncio
async def test_summary_scan_bound_still_has_a_progressing_continuation(browser: Browser) -> None:
    runtime, server, _ = browser
    store = server.routes.automations
    for index in range(258):
        await store.mutate(
            AutomationCreate.model_validate(command(store.instance, name=f"Only {index}")),
            observed_at=NOW,
        )
    first = await runtime.repository.database.read(
        lambda db: store.page_in(db, query="Not present")
    )
    assert not first.automations and first.next_cursor
    second = await runtime.repository.database.read(
        lambda db: store.page_in(db, query="Not present", cursor=first.next_cursor)
    )
    assert not second.automations and second.next_cursor is None


@pytest.mark.asyncio
async def test_read_page_and_revision_are_one_snapshot_during_concurrent_write(
    browser: Browser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, server, _ = browser
    store = server.routes.automations
    ack = await store.mutate(
        AutomationCreate.model_validate(command(store.instance)), observed_at=NOW
    )
    before = await runtime.repository.revision()
    original = store._decode
    applied = False

    def concurrent(row: sqlite3.Row) -> Any:
        nonlocal applied
        if not applied:
            applied = True
            renamed = ack.definition.model_copy(
                update={
                    "entity_version": 2,
                    "spec": ack.definition.spec.model_copy(update={"name": "Concurrent name"}),
                }
            )
            with sqlite3.connect(runtime.repository.database.path) as writer:
                writer.execute("BEGIN IMMEDIATE")
                writer.execute(
                    "UPDATE automation_definitions SET entity_version=2,payload=? "
                    "WHERE automation_id=?",
                    (renamed.model_dump_json(), renamed.automation_id),
                )
                runtime.repository._next_revision(writer)
        return original(row)

    monkeypatch.setattr(store, "_decode", concurrent)
    page = await runtime.repository.database.read(lambda db: store.page_in(db))
    assert page.projection_revision == before and page.automations[0].entity_version == 1
    assert (
        page.automations[0].name == "Fixture Automation"
        and await runtime.repository.revision() == before + 1
    )
    current = await runtime.repository.database.read(
        lambda db: store.detail_in(db, ack.definition.automation_id)
    )
    assert (
        current.definition.entity_version == 2 and current.definition.spec.name == "Concurrent name"
    )


@pytest.mark.asyncio
async def test_foreign_owner_and_global_record_scopes_are_distinct(browser: Browser) -> None:
    runtime, server, client = browser
    global_store = AutomationStore(
        runtime.repository, runtime.config.owner_id, None, server.routes.instance_id
    )
    global_ack = await global_store.mutate(
        AutomationCreate.model_validate(command(global_store.instance, name="Global fixture")),
        observed_at=NOW,
    )
    await runtime.repository.register_owner("foreign-owner")
    foreign_store = AutomationStore(
        runtime.repository, "foreign-owner", None, server.routes.instance_id
    )
    foreign = await foreign_store.mutate(
        AutomationCreate.model_validate(command(foreign_store.instance, name="FOREIGN-SECRET")),
        observed_at=NOW,
    )
    code, page = await client._request_dict("GET", "/api/v1/automations")
    assert code == 200 and [row["automation_id"] for row in page["automations"]] == [
        global_ack.definition.automation_id
    ]
    assert "FOREIGN" not in json.dumps(page)
    assert (
        await client._request_dict("GET", "/api/v1/automations/" + foreign.definition.automation_id)
    )[0] == 404
    assert (
        await client._request_dict("GET", "/api/v1/automation-requests/" + str(foreign.request_id))
    )[0] == 404
