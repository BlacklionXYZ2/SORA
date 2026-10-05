"""Real isolated HTTP/SQLite presentation transport; fake host, not native GUI acceptance."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import pytest
from tests.api.test_memory_browser import Browser, seed
from tests.api.test_memory_browser import browser as browser

from sora.api.protocol import HttpRequest
from sora.api.server import SoraApiServer
from sora.contracts.ui_presentation import UiMemoryCommand, UiPresentationAck
from sora.runtime.ui_presentation import UiPresentationError


async def host(browser: Browser) -> dict[str, Any]:
    _, server, client = browser
    body = {
        "instance_id": server.routes.instance_id,
        "host_id": str(uuid.uuid4()),
        "profile_key": "a" * 64,
        "registry_generation": 0,
    }
    code, lease = await client._request_dict("POST", "/api/v1/ui/host", body)
    assert code == 200
    # Lost initial registration replies are recoverable without a second lease.
    renewed = (await client._request_dict("POST", "/api/v1/ui/host", body))[1]
    assert renewed["lease_id"] == lease["lease_id"] and renewed["host_id"] == lease["host_id"]
    return {k: lease[k] for k in ("instance_id", "host_id", "lease_id")}


def request(browser: Browser, memory: str = "memory-present") -> dict[str, Any]:
    return {
        "instance_id": browser[1].routes.instance_id,
        "request_id": str(uuid.uuid4()),
        "memory_id": memory,
        "expected_version": 1,
    }


def ack(binding: dict[str, Any], body: dict[str, Any], status: str = "selected") -> dict[str, Any]:
    return {
        **binding,
        **body,
        "registry_generation": 1,
        "status": status,
        "panel_visible": status in {"selected", "already-visible"},
        "highlighted": status in {"selected", "already-visible"},
        "selected_id": body["memory_id"] if status in {"selected", "already-visible"} else None,
        "selected_version": 1 if status in {"selected", "already-visible"} else None,
        "anchor": {"x": -100, "y": 50, "width": 600, "height": 300}
        if status in {"selected", "already-visible"}
        else None,
    }


async def events(browser: Browser) -> list[dict[str, Any]]:
    rows = await browser[0].repository.database.read(
        lambda db: db.execute("SELECT payload FROM events").fetchall()
    )
    return [
        event
        for row in rows
        if (event := json.loads(row[0]))["event_type"] == "ui.memory.presented"
    ]


@pytest.mark.asyncio
async def test_dispatch_pending_then_exact_ack_once_and_no_private_payload(
    browser: Browser,
) -> None:
    runtime, _, client = browser
    await seed(
        runtime, "memory-present", content="PRIVATE MEMORY CONTENT", refs=("capture-private",)
    )
    binding = await host(browser)
    body = request(browser)
    revision = await runtime.repository.revision()
    code, queued = await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    assert code == 200 and queued["status"] == "pending" and queued["event_id"] is None
    assert not await events(browser)
    _, page = await client._request_dict("POST", "/api/v1/ui/presentations/poll", binding)
    assert len(page["requests"]) == 1 and page["requests"][0]["memory_id"] == body["memory_id"]
    assert "PRIVATE" not in json.dumps(page) and "capture-private" not in json.dumps(page)
    acknowledgement = ack(binding, body)
    code, selected = await client._request_dict(
        "POST", "/api/v1/ui/presentations/ack", acknowledgement
    )
    assert code == 200 and selected["status"] == "selected" and selected["event_id"]
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/ack", acknowledgement))[
        1
    ] == selected
    assert (await client._request_dict("GET", "/api/v1/ui/presentations/" + body["request_id"]))[
        1
    ] == selected
    assert (await client._request_dict("POST", "/api/v1/ui/present-memory", body))[1] == selected
    assert not (await client._request_dict("POST", "/api/v1/ui/presentations/poll", binding))[1][
        "requests"
    ]
    assert len(await events(browser)) == 1 and await runtime.repository.revision() == revision
    event_text = json.dumps(await events(browser))
    for secret in ("PRIVATE", "capture-private", binding["lease_id"], "anchor", "reasoning"):
        assert secret not in event_text
    outbox = await runtime.repository.database.read(
        lambda db: db.execute(
            "SELECT COUNT(*) FROM outbox WHERE event_id=?", (selected["event_id"],)
        ).fetchone()[0]
    )
    assert outbox == 1
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/presentations/ack", {**acknowledgement, "registry_generation": 2}
        )
    )[1]["error"]["code"] == "UI_ACK_CONFLICT"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["deferred", "unavailable", "rejected", "already-visible"])
async def test_truthful_host_outcomes(browser: Browser, status: str) -> None:
    await seed(browser[0], "memory-present")
    binding, body = await host(browser), request(browser)
    await browser[2]._request_dict("POST", "/api/v1/ui/present-memory", body)
    code, result = await browser[2]._request_dict(
        "POST", "/api/v1/ui/presentations/ack", ack(binding, body, status)
    )
    assert code == 200 and result["status"] == status and len(await events(browser)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"selected_id": "memory-wrong"},
        {"selected_version": 2},
        {"panel_visible": False},
        {"highlighted": False},
        {"anchor": None},
        {"lease_id": str(uuid.uuid4())},
        {"expected_version": 2},
        {"registry_generation": -1},
        {"highlighted": "true"},
        {"authorized_by": "owner"},
    ],
)
async def test_malformed_or_mismatched_ack_never_succeeds(
    browser: Browser, change: dict[str, Any]
) -> None:
    await seed(browser[0], "memory-present")
    binding, body = await host(browser), request(browser)
    await browser[2]._request_dict("POST", "/api/v1/ui/present-memory", body)
    code, _ = await browser[2]._request_dict(
        "POST", "/api/v1/ui/presentations/ack", {**ack(binding, body), **change}
    )
    assert code in {400, 409} and not await events(browser)
    assert browser[0].memory_presentations.result(uuid.UUID(body["request_id"])).status == "pending"


@pytest.mark.asyncio
async def test_scope_deleted_version_changed_epoch_and_no_host(browser: Browser) -> None:
    runtime, _, client = browser
    await seed(runtime, "memory-present")
    assert (await client._request_dict("POST", "/api/v1/ui/present-memory", request(browser)))[1][
        "error"
    ]["code"] == "UI_HOST_UNAVAILABLE"
    binding = await host(browser)
    await runtime.repository.register_owner("other-owner")
    await seed(runtime, "memory-foreign", owner="other-owner", project=None)
    await runtime.repository.register_project("hidden-project", runtime.config.owner_id)
    await seed(runtime, "memory-hidden", project="hidden-project")
    for target in ("memory-foreign", "memory-hidden", "memory-absent"):
        assert (
            await client._request_dict(
                "POST", "/api/v1/ui/present-memory", request(browser, target)
            )
        )[0] == 404
    body = request(browser)
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/present-memory", {**body, "expected_version": 2}
        )
    )[1]["error"]["code"] == "UI_TARGET_CHANGED"
    await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE memories SET deleted_at='deleted' WHERE memory_id='memory-present'"
        )
    )
    code, result = await client._request_dict(
        "POST", "/api/v1/ui/presentations/ack", ack(binding, body)
    )
    assert (
        code == 200 and result["status"] == "unavailable" and result["reason"] == "target-changed"
    )
    # Historical result is not a fresh lookup or automatic selection of a successor.
    assert (await client._request_dict("POST", "/api/v1/ui/present-memory", body))[1] == result
    assert (await client._request_dict("POST", "/api/v1/ui/present-memory", request(browser)))[
        0
    ] == 404
    assert (
        await client._request_dict(
            "POST",
            "/api/v1/ui/host",
            {
                **binding,
                "instance_id": str(uuid.uuid4()),
                "profile_key": "a" * 64,
                "registry_generation": 1,
            },
        )
    )[1]["error"]["code"] == "UI_CORE_CHANGED"


@pytest.mark.asyncio
async def test_queue_binding_caps_expiry_cancel_and_host_loss(browser: Browser) -> None:
    runtime, _, client = browser
    await seed(runtime, "memory-present")
    binding, body = await host(browser), request(browser)
    hub = runtime.memory_presentations
    await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/present-memory", {**body, "expected_version": 2}
        )
    )[1]["error"]["code"] == "UI_REQUEST_CONFLICT"
    for _ in range(31):
        assert (await client._request_dict("POST", "/api/v1/ui/present-memory", request(browser)))[
            0
        ] == 200
    assert (await client._request_dict("POST", "/api/v1/ui/present-memory", request(browser)))[1][
        "error"
    ]["code"] == "UI_QUEUE_FULL"
    assert (
        len(
            (await client._request_dict("POST", "/api/v1/ui/presentations/poll", binding))[1][
                "requests"
            ]
        )
        == 16
    )
    hub.requests[uuid.UUID(body["request_id"])].deadline = time.monotonic() - 1
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/ack", ack(binding, body)))[
        1
    ]["status"] == "expired"
    assert not await events(browser)
    cancelled = request(browser)
    await client._request_dict("POST", "/api/v1/ui/present-memory", cancelled)
    hub.cancel(uuid.UUID(cancelled["request_id"]))
    assert (
        await client._request_dict("POST", "/api/v1/ui/presentations/ack", ack(binding, cancelled))
    )[1]["reason"] == "turn-cancelled"
    assert hub.host is not None
    hub.host.deadline = time.monotonic() - 1
    assert (
        hub.result(
            next(key for key, item in hub.requests.items() if item.result.status == "pending")
        ).reason
        == "host-lost"
    )
    await host(browser)
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/poll", binding))[1][
        "error"
    ]["code"] == "UI_HOST_UNAVAILABLE"


@pytest.mark.asyncio
async def test_concurrent_admission_ack_and_lost_response_are_single_event(
    browser: Browser,
) -> None:
    runtime, _, client = browser
    await seed(runtime, "memory-present")
    binding, body = await host(browser), request(browser)
    results = await asyncio.gather(
        *(client._request_dict("POST", "/api/v1/ui/present-memory", body) for _ in range(4))
    )
    assert (
        all(code == 200 for code, _ in results) and len(runtime.memory_presentations.requests) == 1
    )
    command = UiPresentationAck.model_validate(ack(binding, body))
    db = runtime.repository.database
    await db._write_lock.acquire()
    pending = asyncio.create_task(runtime.memory_presentations.acknowledge(command))
    await asyncio.sleep(0)
    pending.cancel()
    db._write_lock.release()
    with pytest.raises(asyncio.CancelledError):
        await pending
    result = await runtime.memory_presentations.acknowledge(command)
    assert result.status == "selected" and len(await events(browser)) == 1


@pytest.mark.asyncio
async def test_expiry_during_atomic_write_wait_does_not_publish_success(browser: Browser) -> None:
    runtime, _, client = browser
    await seed(runtime, "memory-present")
    binding, body = await host(browser), request(browser)
    await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    db, hub = runtime.repository.database, runtime.memory_presentations
    await db._write_lock.acquire()
    pending = asyncio.create_task(
        hub.acknowledge(UiPresentationAck.model_validate(ack(binding, body)))
    )
    await asyncio.sleep(0)
    hub.requests[uuid.UUID(body["request_id"])].deadline = time.monotonic() - 1
    db._write_lock.release()
    assert (await pending).status == "expired" and not await events(browser)


@pytest.mark.asyncio
async def test_closed_methods_remote_and_ephemeral_epoch_reset(browser: Browser) -> None:
    runtime, server, client = browser
    binding = await host(browser)
    for method, path in [
        ("POST", "/api/v1/ui/host"),
        ("POST", "/api/v1/ui/present-memory"),
        ("POST", "/api/v1/ui/presentations/poll"),
        ("POST", "/api/v1/ui/presentations/ack"),
        ("GET", "/api/v1/ui/presentations/" + str(uuid.uuid4())),
    ]:
        response = await server.routes.handle_request(
            HttpRequest(method, path, {}, b"{}"), remote_scopes=frozenset({"memory.read"})
        )
        assert response.status_code == 403
    assert (await client._request_dict("GET", "/api/v1/ui/host"))[0] == 405
    assert (
        await client._request_dict("POST", "/api/v1/ui/present-memory?extra=1", request(browser))
    )[0] == 400
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/present-memory", {**request(browser), "origin": "companion"}
        )
    )[0] == 400
    runtime.memory_presentations.bind(str(uuid.uuid4()))
    assert not runtime.memory_presentations.requests
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/poll", binding))[1][
        "error"
    ]["code"] == "UI_CORE_CHANGED"


@pytest.mark.asyncio
async def test_companion_activation_binding_and_dialogue_correlation(browser: Browser) -> None:
    runtime, _, _ = browser
    await seed(runtime, "memory-present")
    await host(browser)
    hub = runtime.memory_presentations
    command = UiMemoryCommand.model_validate(request(browser))
    result = await hub.request(
        command, companion=True, dialogue_request_id="dialogue-fixture", passive=True
    )
    assert result.status == "pending"
    pending = hub.requests[command.request_id].request
    assert (
        pending.origin == "companion"
        and pending.activation == "passive"
        and pending.dialogue_request_id == "dialogue-fixture"
    )
    with pytest.raises(UiPresentationError, match="UI_REQUEST_CONFLICT"):
        await hub.request(
            command, companion=True, dialogue_request_id="dialogue-fixture", passive=False
        )


@pytest.mark.asyncio
async def test_host_profile_lease_generation_conflict_and_duplicate_historical_ack(
    browser: Browser,
) -> None:
    _, _, client = browser
    await seed(browser[0], "memory-present")
    binding, body = await host(browser), request(browser)
    registration = {**binding, "profile_key": "a" * 64, "registry_generation": 2}
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/host", {**registration, "profile_key": "b" * 64}
        )
    )[1]["error"]["code"] == "UI_HOST_CONFLICT"
    assert (
        await client._request_dict(
            "POST", "/api/v1/ui/host", {**registration, "lease_id": str(uuid.uuid4())}
        )
    )[1]["error"]["code"] == "UI_STALE_REGISTRY"
    await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    await client._request_dict("POST", "/api/v1/ui/host", registration)
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/ack", ack(binding, body)))[
        1
    ]["error"]["code"] == "UI_STALE_REGISTRY"
    acknowledgement = {**ack(binding, body), "registry_generation": 2}
    _, original = await client._request_dict(
        "POST", "/api/v1/ui/presentations/ack", acknowledgement
    )
    await client._request_dict(
        "POST", "/api/v1/ui/host", {**registration, "registry_generation": 3}
    )
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/ack", acknowledgement))[
        1
    ] == original
    assert len(await events(browser)) == 1


@pytest.mark.asyncio
async def test_event_outbox_failure_rolls_back_and_remote_stream_strips_ids(
    browser: Browser, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-present", content="PRIVATE-CONTENT")
    binding, body = await host(browser), request(browser)
    await client._request_dict("POST", "/api/v1/ui/present-memory", body)
    original = runtime.repository._append_event

    def broken(*args: Any, **kwargs: Any) -> str:
        original(*args, **kwargs)
        raise RuntimeError("PRIVATE-DIAGNOSTICS")

    monkeypatch.setattr(runtime.repository, "_append_event", broken)
    code, error = await client._request_dict(
        "POST", "/api/v1/ui/presentations/ack", ack(binding, body)
    )
    assert code == 500 and "PRIVATE" not in json.dumps(error) and not await events(browser)
    assert runtime.memory_presentations.result(uuid.UUID(body["request_id"])).status == "pending"
    monkeypatch.setattr(runtime.repository, "_append_event", original)
    assert (await client._request_dict("POST", "/api/v1/ui/presentations/ack", ack(binding, body)))[
        1
    ]["status"] == "selected"
    response = await server.routes.handle_request(
        HttpRequest("GET", "/api/v1/events?since=0", {}, b"")
    )
    remote = SoraApiServer._sanitize_remote_events(response).parse_json()
    serialized = json.dumps(remote)
    assert "ui.memory.presented" in serialized
    for private in (body["memory_id"], body["request_id"], binding["host_id"], "PRIVATE", "anchor"):
        assert private not in serialized
