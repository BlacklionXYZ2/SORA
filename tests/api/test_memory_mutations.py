"""Versioned memory lifecycle against actual isolated HTTP/SQLite; no owner writes."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pytest
from tests.api.test_memory_browser import Browser, seed
from tests.api.test_memory_browser import browser as browser

from sora.api.protocol import HttpRequest
from sora.contracts.memory_browser import MemoryCorrection, MemoryMutationAck
from sora.memory.captures import CaptureRecord, compact_captures, write_capture
from sora.persistence.backup import create_backup, restore_backup
from sora.persistence.database import SQLiteDatabase
from sora.persistence.repository import SoraRepository
from sora.runtime.memory_mutations import mutate, receipt


def command(instance: str, *, correct: bool = True, version: int = 1) -> dict[str, object]:
    body: dict[str, object] = {
        "instance_id": instance,
        "request_id": str(uuid.uuid4()),
        "expected_version": version,
    }
    if correct:
        body["content"] = "Updated owner preference 🐱"
    return body


@pytest.mark.asyncio
async def test_correction_versions_retrieval_receipt_event_and_evidence(browser: Browser) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-edit", refs=("capture-private",))
    body = command(server.routes.instance_id)
    before = await runtime.repository.revision()
    code, payload = await client._request_dict("POST", "/api/v1/memories/memory-edit/correct", body)
    ack = MemoryMutationAck.model_validate(payload)
    assert code == 200 and ack.entity_version == 2 and ack.expected_version == 1
    assert ack.successor_id and ack.successor_version == 1 and not ack.replayed
    assert ack.projection_revision == before + 1
    memories = await runtime.repository.list_memories(
        runtime.config.owner_id, project_id=runtime.config.project_id, observed_at=datetime.now(UTC)
    )
    assert [(m.memory_id, m.content) for m in memories] == [(ack.successor_id, body["content"])]
    assert memories[0].evidence_refs == () and memories[0].retention == "durable"
    _, old = await client._request_dict("GET", "/api/v1/memories/memory-edit")
    assert old["memory"]["state"] == "superseded" and old["memory"]["entity_version"] == 2
    event = await runtime.repository.database.read(
        lambda db: json.loads(
            db.execute("SELECT payload FROM events WHERE event_id=?", (ack.event_id,)).fetchone()[0]
        )
    )
    assert (
        event["payload"]["memory_id"] == "memory-edit"
        and event["payload"]["request_id"] == body["request_id"]
    )
    assert event["payload"]["successor_id"] == ack.successor_id
    assert "Updated owner" not in json.dumps(event) and "capture-private" not in json.dumps(event)
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute(
                "SELECT COUNT(*) FROM outbox WHERE event_id=?", (ack.event_id,)
            ).fetchone()[0]
        )
        == 1
    )
    code, again = await client._request_dict("POST", "/api/v1/memories/memory-edit/correct", body)
    assert code == 200 and again["replayed"] and again["event_id"] == ack.event_id
    assert await runtime.repository.revision() == before + 1
    _, historical = await client._request_dict(
        "GET", "/api/v1/memory-mutations/" + str(body["request_id"])
    )
    assert historical["replayed"] and historical["successor_id"] == ack.successor_id
    assert (
        "Updated owner" not in json.dumps(historical) and "No Undo" in historical["retention_note"]
    )
    code, conflict = await client._request_dict(
        "POST", "/api/v1/memories/memory-edit/correct", {**body, "content": "different"}
    )
    assert code == 409 and conflict["error"]["code"] == "MEMORY_REQUEST_CONFLICT"


@pytest.mark.asyncio
async def test_forget_exact_predecessor_then_successor_and_no_resurrection(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-forget")
    root = runtime.config.root / "captures"
    capture = write_capture(
        root,
        CaptureRecord(
            capture_id="capture-forget",
            memory_id="memory-forget",
            created_at=datetime.now(UTC),
            owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id,
            provider="fixture",
            owner_text="private words",
            response_text="private response",
            reasoning="PRIVATE-REASONING",
        ),
    )
    _, corrected = await client._request_dict(
        "POST", "/api/v1/memories/memory-forget/correct", command(server.routes.instance_id)
    )
    successor = str(corrected["successor_id"])
    body = command(server.routes.instance_id, correct=False, version=2)
    code, ack = await client._request_dict("POST", "/api/v1/memories/memory-forget/forget", body)
    assert code == 200 and ack["entity_version"] == 3 and ack["successor_id"] is None
    assert capture.exists() and "PRIVATE-REASONING" not in json.dumps(ack)
    assert (await client._request_dict("GET", "/api/v1/memories/memory-forget"))[0] == 404
    _, page = await client._request_dict("GET", "/api/v1/memories?state=all")
    assert [m["memory_id"] for m in page["memories"]] == [successor]
    code, _ = await client._request_dict(
        "POST",
        f"/api/v1/memories/{successor}/forget",
        command(server.routes.instance_id, correct=False),
    )
    assert code == 200
    await asyncio.to_thread(compact_captures, root, now=datetime.now(UTC), retention_days=30)
    assert capture.exists()
    assert (
        await runtime.repository.list_memories(
            runtime.config.owner_id,
            project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC),
        )
        == []
    )
    _, empty = await client._request_dict("GET", "/api/v1/memories?state=all")
    assert empty["memories"] == []
    assert (await client._request_dict("POST", "/api/v1/memories/memory-forget/forget", body))[1][
        "replayed"
    ] is True


@pytest.mark.asyncio
async def test_two_writers_only_one_successor_and_safe_conflict(browser: Browser) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-race")
    results = await asyncio.gather(
        *(
            client._request_dict(
                "POST", "/api/v1/memories/memory-race/correct", command(server.routes.instance_id)
            )
            for _ in range(2)
        )
    )
    assert sorted(code for code, _ in results) == [200, 409]
    error = next(payload["error"] for code, payload in results if code == 409)
    assert error["current_version"] == 2 and error["current_state"] == "superseded"
    assert error["code"] == "MEMORY_VERSION_CONFLICT"
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        )
        == 2
    )


@pytest.mark.asyncio
async def test_scope_guard_remote_epoch_and_receipt_scope(browser: Browser) -> None:
    runtime, server, client = browser
    await runtime.repository.register_owner("other-owner")
    await runtime.repository.register_project("other-project", "other-owner")
    await runtime.repository.register_project("hidden-project", runtime.config.owner_id)
    for memory_id, owner, project in (
        ("memory-foreign", "other-owner", "other-project"),
        ("memory-hidden", None, "hidden-project"),
    ):
        await seed(runtime, memory_id, owner=owner, project=project)
        for action in ("correct", "forget"):
            code, payload = await client._request_dict(
                "POST",
                f"/api/v1/memories/{memory_id}/{action}",
                command(server.routes.instance_id, correct=action == "correct"),
            )
            assert code == 404 and "current_version" not in json.dumps(payload)
    await seed(runtime, "memory-local", project=None)
    for action in ("correct", "forget"):
        path = f"/api/v1/memories/memory-local/{action}"
        remote = await server.routes.handle_request(
            HttpRequest("POST", path, {}, b"{}"),
            remote_scopes=frozenset({"memory.read", "memory.write"}),
        )
        assert remote.status_code == 403
        assert (
            await client._request_dict(
                "POST", path, command(str(uuid.uuid4()), correct=action == "correct")
            )
        )[0] == 409
    body = command(server.routes.instance_id, correct=False)
    assert (await client._request_dict("POST", "/api/v1/memories/memory-local/forget", body))[
        0
    ] == 200
    path = "/api/v1/memory-mutations/" + str(body["request_id"])
    assert (
        await server.routes.handle_request(
            HttpRequest("GET", path, {}, b""), remote_scopes=frozenset({"memory.read"})
        )
    ).status_code == 403
    with pytest.raises(LookupError):
        await runtime.repository.database.read(
            partial(
                receipt,
                owner=runtime.config.owner_id,
                project="hidden-project",
                request_id=uuid.UUID(str(body["request_id"])),
                instance=server.routes.instance_id,
            )
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": "other"},
        {"authorized_by": "owner"},
        {"expected_version": True},
        {"expected_version": 1.0},
        {"expected_version": "1"},
        {"expected_version": 0},
        {"request_id": "bad"},
        {"content": " "},
        {"content": "bad\u0000text"},
        {"content": "x" * 16385},
    ],
)
async def test_closed_validation_has_no_effect(
    browser: Browser, changes: dict[str, object]
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-valid")
    before = await runtime.repository.revision()
    code, payload = await client._request_dict(
        "POST",
        "/api/v1/memories/memory-valid/correct",
        {**command(server.routes.instance_id), **changes},
    )
    assert code == 400 and payload["error"]["code"] == "INVALID_MEMORY_MUTATION"
    assert await runtime.repository.revision() == before


@pytest.mark.asyncio
async def test_expiry_preservation_and_state_guards(browser: Browser) -> None:
    runtime, server, client = browser
    future = datetime.now(UTC) + timedelta(hours=1)
    await seed(runtime, "memory-future", until=future)
    await seed(runtime, "memory-expired", until=datetime.now(UTC) - timedelta(seconds=1))
    code, error = await client._request_dict(
        "POST", "/api/v1/memories/memory-expired/correct", command(server.routes.instance_id)
    )
    assert code == 409 and error["error"]["code"] == "MEMORY_STATE_CONFLICT"
    _, ack = await client._request_dict(
        "POST", "/api/v1/memories/memory-future/correct", command(server.routes.instance_id)
    )
    _, latest = await client._request_dict("GET", "/api/v1/memories/" + str(ack["successor_id"]))
    assert datetime.fromisoformat(str(latest["memory"]["valid_until"])) == future
    assert (
        await client._request_dict(
            "POST",
            "/api/v1/memories/memory-expired/forget",
            command(server.routes.instance_id, correct=False),
        )
    )[0] == 200


@pytest.mark.asyncio
async def test_receipt_insert_failure_rolls_back_everything(browser: Browser) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-rollback")
    before = await runtime.repository.revision()
    await runtime.repository.database.write(
        lambda db: db.execute(
            "CREATE TRIGGER reject_receipt BEFORE INSERT ON memory_mutation_receipts "
            "BEGIN SELECT RAISE(ABORT, 'private diagnostic'); END"
        )
    )
    code, payload = await client._request_dict(
        "POST", "/api/v1/memories/memory-rollback/correct", command(server.routes.instance_id)
    )
    assert code == 503 and "private diagnostic" not in json.dumps(payload)
    assert await runtime.repository.revision() == before
    _, original = await client._request_dict("GET", "/api/v1/memories/memory-rollback")
    assert original["memory"]["entity_version"] == 1 and original["memory"]["state"] == "active"
    assert (
        await runtime.repository.database.read(
            lambda db: db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        )
        == 1
    )


@pytest.mark.asyncio
async def test_receipt_backup_restore_and_new_instance_retry(
    browser: Browser, tmp_path: Path
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-backup")
    body = command(server.routes.instance_id)
    _, ack = await client._request_dict("POST", "/api/v1/memories/memory-backup/correct", body)
    assert (
        await client._request_dict(
            "POST",
            "/api/v1/memories/" + str(ack["successor_id"]) + "/forget",
            command(server.routes.instance_id, correct=False),
        )
    )[0] == 200
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    archive = await create_backup(
        runtime.repository.database, artifacts_root=artifacts, destination=tmp_path / "backup"
    )
    await restore_backup(backup=archive.parent, destination=tmp_path / "restored")
    paths = list((tmp_path / "restored").rglob("*.db"))
    assert len(paths) == 1
    restored = SQLiteDatabase(paths[0])
    await restored.initialize()
    new_instance = str(uuid.uuid4())
    request = MemoryCorrection.model_validate({**body, "instance_id": new_instance})
    replay = await mutate(
        SoraRepository(restored),
        owner=runtime.config.owner_id,
        project=runtime.config.project_id,
        memory_id="memory-backup",
        instance=new_instance,
        request=request,
    )
    assert replay.instance_id == uuid.UUID(
        new_instance
    ) and replay.committed_instance_id == uuid.UUID(server.routes.instance_id)
    assert (
        replay.replayed
        and replay.event_id == ack["event_id"]
        and replay.successor_id == ack["successor_id"]
    )
    assert (
        await restored.read(
            lambda db: db.execute("SELECT COUNT(*) FROM memory_mutation_receipts").fetchone()[0]
        )
        == 2
    )
    assert (
        await SoraRepository(restored).list_memories(
            runtime.config.owner_id,
            project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC),
        )
        == []
    )


@pytest.mark.asyncio
async def test_correction_and_forget_change_actual_compiled_dialogue_memory(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-context", content="MEMORY_ONLY_OLD_719")
    context, _ = await runtime._direct_dialogue_context(
        "What do you remember?", allow_history=False, allow_task_context=False
    )
    assert "MEMORY_ONLY_OLD_719" in context
    body = {**command(server.routes.instance_id), "content": "MEMORY_ONLY_NEW_882"}
    _, ack = await client._request_dict("POST", "/api/v1/memories/memory-context/correct", body)
    context, _ = await runtime._direct_dialogue_context(
        "What do you remember?", allow_history=False, allow_task_context=False
    )
    assert "MEMORY_ONLY_NEW_882" in context and "MEMORY_ONLY_OLD_719" not in context
    assert (
        await client._request_dict(
            "POST",
            "/api/v1/memories/" + str(ack["successor_id"]) + "/forget",
            command(server.routes.instance_id, correct=False),
        )
    )[0] == 200
    context, _ = await runtime._direct_dialogue_context(
        "What do you remember?", allow_history=False, allow_task_context=False
    )
    assert "MEMORY_ONLY_NEW_882" not in context and "MEMORY_ONLY_OLD_719" not in context


@pytest.mark.asyncio
async def test_migration_ten_preserves_canonical_rows_and_adds_empty_receipts(
    tmp_path: Path,
) -> None:
    db = SQLiteDatabase(tmp_path / "previous.db")
    await db.initialize(target_version=10)
    repository = SoraRepository(db)
    await repository.register_owner("owner-old")
    await repository.add_memory(
        memory_id="memory-old",
        owner_id="owner-old",
        project_id=None,
        content="Preserved",
        scope="dialogue",
        sensitivity="private",
        retention="durable",
        provenance="owner",
    )
    before = await repository.list_memories(
        "owner-old", project_id=None, observed_at=datetime.now(UTC)
    )
    revision = await repository.revision()
    await db.initialize()
    assert await db.schema_version() == 15 and await repository.revision() == revision
    assert (
        await repository.list_memories("owner-old", project_id=None, observed_at=datetime.now(UTC))
        == before
    )
    assert (
        await db.read(
            lambda connection: connection.execute(
                "SELECT COUNT(*) FROM memory_mutation_receipts"
            ).fetchone()[0]
        )
        == 0
    )


@pytest.mark.asyncio
async def test_corrupt_canonical_rows_and_receipts_are_redacted(browser: Browser) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-corrupt")
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE memories SET evidence_json='PRIVATE-DIAGNOSTIC' "
            "WHERE memory_id='memory-corrupt'"
        )
    )
    code, error = await client._request_dict(
        "POST", "/api/v1/memories/memory-corrupt/correct", command(server.routes.instance_id)
    )
    assert code == 503 and "PRIVATE-DIAGNOSTIC" not in json.dumps(error)
    await seed(runtime, "memory-receipt-corrupt")
    body = command(server.routes.instance_id, correct=False)
    assert (
        await client._request_dict("POST", "/api/v1/memories/memory-receipt-corrupt/forget", body)
    )[0] == 200
    await runtime.repository.database.write(
        lambda db: db.execute("UPDATE memory_mutation_receipts SET payload='PRIVATE-RECEIPT'")
    )
    code, error = await client._request_dict(
        "GET", "/api/v1/memory-mutations/" + str(body["request_id"])
    )
    assert code == 503 and "PRIVATE-RECEIPT" not in json.dumps(error)
