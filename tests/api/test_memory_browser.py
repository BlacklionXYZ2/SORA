"""Canonical Memory HTTP fixtures, not native GUI or live-model acceptance."""

from __future__ import annotations

import base64
import json
import sqlite3
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path
from urllib.parse import urlencode

import pytest
import pytest_asyncio

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.contracts.content import ContentReference
from sora.contracts.memory_browser import MemoryPage
from sora.providers.mock import DeterministicProvider
from sora.runtime.memory_browser import memory_detail, memory_page
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"
NOW = datetime(2026, 10, 4, 8, tzinfo=UTC)
type Browser = tuple[SoraRuntime, SoraApiServer, SoraApiClient]


@pytest_asyncio.fixture
async def browser(tmp_path: Path) -> AsyncIterator[Browser]:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime", identity_root=IDENTITY_ROOT, content_roots=(tmp_path,)
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="memory-browser-test"))
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token="memory-browser-test"
    )
    try:
        yield runtime, server, client
    finally:
        await server.close()
        await runtime.close()


async def seed(
    runtime: SoraRuntime,
    memory_id: str,
    *,
    content: str = "Owner fixture preference",
    project: str | None = "current",
    owner: str | None = None,
    scope: str = "dialogue",
    until: datetime | None = None,
    refs: tuple[str, ...] = (),
) -> None:
    await runtime.repository.add_memory(
        memory_id=memory_id,
        owner_id=owner or runtime.config.owner_id,
        project_id=runtime.config.project_id if project == "current" else project,
        content=content,
        scope=scope,
        sensitivity="private",
        retention="durable",
        provenance="owner-stated fixture",
        valid_until=until,
        evidence_refs=refs,
    )


@pytest.mark.asyncio
async def test_http_empty_page_and_exact_owner_project_scope(browser: Browser) -> None:
    runtime, server, client = browser
    code, empty = await client._request_dict("GET", "/api/v1/memories")
    assert code == 200 and empty["memories"] == [] and empty["next_cursor"] is None
    assert empty["instance_id"] == server.routes.instance_id
    assert empty["projection_revision"] >= 0 and empty["observed_at"]
    await seed(runtime, "memory-project")
    await seed(runtime, "memory-global", project=None)
    await runtime.repository.register_owner("other-owner")
    await runtime.repository.register_project("other-project", "other-owner")
    await runtime.repository.register_project("hidden-project", runtime.config.owner_id)
    await seed(
        runtime,
        "memory-foreign",
        owner="other-owner",
        project="other-project",
        content="OTHER OWNER SECRET",
    )
    await seed(
        runtime, "memory-hidden-project", project="hidden-project", content="OTHER PROJECT SECRET"
    )
    _, all_rows = await client._request_dict("GET", "/api/v1/memories")
    assert [m["memory_id"] for m in all_rows["memories"]] == ["memory-global", "memory-project"]
    assert "SECRET" not in json.dumps(all_rows)
    for project, expected in (("global", "memory-global"), ("project", "memory-project")):
        _, page = await client._request_dict("GET", "/api/v1/memories?project=" + project)
        assert [m["memory_id"] for m in page["memories"]] == [expected]
    for memory_id in ("memory-foreign", "memory-hidden-project", "memory-unknown"):
        code, reply = await client._request_dict("GET", "/api/v1/memories/" + memory_id)
        assert (
            code == 404
            and reply["error"]["code"] == "NOT_FOUND"
            and "SECRET" not in json.dumps(reply)
        )


@pytest.mark.asyncio
async def test_paging_ceiling_signed_filter_binding_refresh_and_live_deletion(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    for i in range(5):
        await seed(runtime, f"memory-{i}")
    code, first = await client._request_dict("GET", "/api/v1/memories?limit=2")
    assert code == 200 and first["total"] == 5
    assert [m["memory_id"] for m in first["memories"]] == ["memory-4", "memory-3"]
    cursor = first["next_cursor"]
    await seed(runtime, "memory-new")
    await runtime.repository.delete_memory("memory-4", deleted_at=datetime.now(UTC))
    _, second = await client._request_dict("GET", "/api/v1/memories?limit=2&cursor=" + cursor)
    assert [m["memory_id"] for m in second["memories"]] == ["memory-2", "memory-1"]
    assert second["total"] == 4 and second["projection_revision"] > first["projection_revision"]
    _, third = await client._request_dict(
        "GET", "/api/v1/memories?limit=2&cursor=" + second["next_cursor"]
    )
    assert [m["memory_id"] for m in third["memories"]] == ["memory-0"] and third[
        "next_cursor"
    ] is None
    _, fresh = await client._request_dict("GET", "/api/v1/memories")
    assert fresh["memories"][0]["memory_id"] == "memory-new"
    for extra in ("&q=preference", "&state=all", "&scope=dialogue", "&project=global"):
        code, reply = await client._request_dict(
            "GET", "/api/v1/memories?limit=2&cursor=" + cursor + extra
        )
        assert code == 400 and reply["error"]["code"] == "INVALID_MEMORY_QUERY"
    raw = bytearray(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    raw[3] ^= 1
    forged = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    code, _ = await client._request_dict("GET", "/api/v1/memories?limit=2&cursor=" + forged)
    assert code == 400
    for owner, project, instance, key in (
        ("other-owner", None, server.routes.instance_id, server.routes._memory_cursor_key),
        (
            runtime.config.owner_id,
            None,
            server.routes.instance_id,
            server.routes._memory_cursor_key,
        ),
        (
            runtime.config.owner_id,
            runtime.config.project_id,
            str(uuid.uuid4()),
            server.routes._memory_cursor_key,
        ),
        (
            runtime.config.owner_id,
            runtime.config.project_id,
            server.routes.instance_id,
            b"different-key",
        ),
    ):
        with pytest.raises(ValueError):
            await runtime.repository.database.read(
                partial(
                    memory_page,
                    owner=owner,
                    project_id=project,
                    instance=instance,
                    key=key,
                    limit=2,
                    cursor=cursor,
                )
            )


@pytest.mark.asyncio
async def test_states_expiry_timezone_supersession_deleted_never_follows_another_id(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-active")
    await seed(runtime, "memory-expired", until=NOW - timedelta(seconds=1))
    await seed(runtime, "memory-boundary", until=NOW.astimezone().replace(microsecond=0))
    await seed(runtime, "memory-old")
    await runtime.repository.correct_memory(
        "memory-old",
        replacement_id="memory-successor",
        content="Corrected fixture",
        provenance="owner correction",
    )
    await seed(runtime, "memory-deleted", content="DELETED CONTENT")
    await runtime.repository.delete_memory("memory-deleted", deleted_at=NOW)

    async def page(state: str) -> MemoryPage:
        return await runtime.repository.database.read(
            lambda db: memory_page(
                db,
                owner=runtime.config.owner_id,
                project_id=runtime.config.project_id,
                instance=server.routes.instance_id,
                key=server.routes._memory_cursor_key,
                state=state,
                observed_at=NOW,
            )
        )

    assert {m.memory_id for m in (await page("active")).memories} == {
        "memory-active",
        "memory-successor",
    }
    assert {m.memory_id for m in (await page("expired")).memories} == {
        "memory-expired",
        "memory-boundary",
    }
    assert [m.memory_id for m in (await page("superseded")).memories] == ["memory-old"]
    assert len((await page("all")).memories) == 5
    _, detail = await client._request_dict("GET", "/api/v1/memories/memory-old")
    assert detail["memory"]["memory_id"] == "memory-old" and detail["memory"]["entity_version"] == 2
    assert detail["memory"]["superseded_by"] == "memory-successor"
    code, deleted = await client._request_dict("GET", "/api/v1/memories/memory-deleted")
    assert code == 404 and "DELETED CONTENT" not in json.dumps(deleted)
    await runtime.repository.delete_memory("memory-successor", deleted_at=NOW)
    _, old = await client._request_dict("GET", "/api/v1/memories/memory-old")
    assert old["memory"]["memory_id"] == "memory-old" and old["memory"]["superseded_by"] is None


@pytest.mark.asyncio
async def test_literal_search_metadata_filter_bounded_preview_and_no_invented_metrics(
    browser: Browser,
) -> None:
    runtime, _, client = browser
    await seed(
        runtime, "memory-percent", content="Use 100%_exact \\ paths; ' OR 1=1 --", scope="work"
    )
    await seed(runtime, "memory-other", content="Use 100XXexact paths", scope="dialogue")
    await seed(runtime, "memory-long", content="x" * 16384)
    for query in ("100%_exact", "\\", "' OR 1=1 --", "USE 100%"):
        code, page = await client._request_dict(
            "GET", "/api/v1/memories?" + urlencode({"q": query})
        )
        assert code == 200 and [m["memory_id"] for m in page["memories"]] == ["memory-percent"]
    _, filtered = await client._request_dict("GET", "/api/v1/memories?scope=work")
    assert filtered["total"] == 1
    _, page = await client._request_dict("GET", "/api/v1/memories?q=xxxxxxxx")
    summary = page["memories"][0]
    assert len(summary["content_preview"]) == 512 and summary["content_truncated"] is True
    assert (
        not {"content", "evidence_json", "created_at", "importance", "relevance", "reasoning"}
        & summary.keys()
    )
    _, detail = await client._request_dict("GET", "/api/v1/memories/memory-long")
    assert len(detail["memory"]["content"]) == 16384
    assert (
        not {"created_at", "importance", "relevance", "reasoning", "rationale"}
        & detail["memory"].keys()
    )


@pytest.mark.asyncio
async def test_expiry_matches_canonical_repository_at_microsecond_boundaries(
    browser: Browser,
) -> None:
    runtime, server, _ = browser
    for name, delta in (("before", -1), ("equal", 0), ("after", 1)):
        await seed(runtime, "memory-" + name, until=NOW + timedelta(microseconds=delta))
    canonical = await runtime.repository.list_memories(
        runtime.config.owner_id,
        project_id=runtime.config.project_id,
        observed_at=NOW,
    )
    page = await runtime.repository.database.read(
        partial(
            memory_page,
            owner=runtime.config.owner_id,
            project_id=runtime.config.project_id,
            instance=server.routes.instance_id,
            key=server.routes._memory_cursor_key,
            observed_at=NOW,
        )
    )
    assert (
        [m.memory_id for m in page.memories] == [m.memory_id for m in canonical] == ["memory-after"]
    )


@pytest.mark.asyncio
async def test_only_registered_live_owner_device_project_evidence_no_private_capture(
    browser: Browser, tmp_path: Path
) -> None:
    runtime, server, client = browser
    client.device_id = "device-local"
    (tmp_path / "file.txt").write_text("Synthetic registered evidence\n", encoding="utf-8")
    reference = ContentReference(
        reference_id="content-good",
        kind="file",
        label="Owner evidence",
        owner_id=runtime.config.owner_id,
        device_id=client.device_id,
        project_id=runtime.config.project_id,
        path=tmp_path / "file.txt",
        root=tmp_path,
        created_at=datetime.now(UTC),
    )
    runtime.register_content_reference(reference)
    private = reference.model_copy(update={"reference_id": "capture-private"})
    runtime.register_content_reference(private)
    capture_path = runtime.config.root / "captures" / "private.json"
    capture_path.parent.mkdir(parents=True, exist_ok=True)
    capture_path.write_text('{"reasoning":"PRIVATE-CAPTURE-REASONING"}', encoding="utf-8")
    capture_ref = reference.model_copy(
        update={"reference_id": "content-capture-file", "path": capture_path}
    )
    runtime.register_content_reference(capture_ref)
    await seed(
        runtime,
        "memory-evidence",
        refs=("content-good", "capture-private", "unregistered", "content-capture-file"),
    )
    _, detail = await client._request_dict("GET", "/api/v1/memories/memory-evidence")
    assert [e["reference_id"] for e in detail["memory"]["evidence"]] == ["content-good"]
    assert detail["memory"]["evidence_withheld"] is True
    assert "capture-private" not in json.dumps(detail) and "unregistered" not in json.dumps(detail)
    assert "content-capture-file" not in json.dumps(
        detail
    ) and "PRIVATE-CAPTURE-REASONING" not in json.dumps(detail)
    assert str(tmp_path) not in json.dumps(detail)
    for field, value in (
        ("owner_id", "other-owner"),
        ("project_id", "other-project"),
        ("device_id", "other-device"),
    ):
        foreign = reference.model_copy(update={field: value})
        result = await runtime.repository.database.read(
            partial(
                memory_detail,
                owner=runtime.config.owner_id,
                project_id=runtime.config.project_id,
                memory_id="memory-evidence",
                instance=server.routes.instance_id,
                device=client.device_id,
                references=(foreign,),
            )
        )
        assert result.memory.evidence == ()
    client.device_id = "device-other"
    _, other = await client._request_dict("GET", "/api/v1/memories/memory-evidence")
    assert other["memory"]["evidence"] == []
    runtime.reference_resolver.clear()
    _, missing = await client._request_dict("GET", "/api/v1/memories/memory-evidence")
    assert missing["memory"]["evidence"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=-1",
        "limit=+1",
        "limit=garbage",
        "limit=",
        "limit=1&limit=2",
        "state=deleted",
        "state=",
        "project=other-project",
        "owner_id=other-owner",
        "scope=" + "x" * 129,
        "q=" + "x" * 257,
        "q=a%00b",
        "q=a%0ab",
        "cursor=",
        "cursor=bad!",
        "unexpected=true",
    ],
)
async def test_closed_bounded_query_rejects_invalid_and_duplicate_fields(
    browser: Browser,
    query: str,
) -> None:
    _, _, client = browser
    code, reply = await client._request_dict("GET", "/api/v1/memories?" + query)
    assert code == 400 and reply["error"]["code"] == "INVALID_MEMORY_QUERY"


@pytest.mark.asyncio
async def test_readonly_owner_local_remote_epoch_and_unsupported_detail_query(
    browser: Browser,
) -> None:
    runtime, server, client = browser
    await seed(runtime, "memory-local")
    for path in ("/api/v1/memories", "/api/v1/memories/memory-local"):
        for method in ("GET", "POST", "DELETE"):
            remote = await server.routes.handle_request(
                HttpRequest(method, path, {}, b""),
                remote_scopes=frozenset({"tasks.read", "memory.read"}),
            )
            assert remote.status_code == 403
        code, _ = await client._request_dict("POST", path, {"content": "Must not change"})
        assert code == 405
        changed = await server.routes.handle_request(
            HttpRequest("GET", path, {"X-SORA-Core-Instance": str(uuid.uuid4())}, b"")
        )
        assert changed.status_code == 409
    for path in (
        "memory-local?owner_id=other",
        "memory-local?cursor=x",
        "memory-local/extra",
        "%2e%2e",
    ):
        code, _ = await client._request_dict("GET", "/api/v1/memories/" + path)
        assert code == 400


@pytest.mark.asyncio
async def test_large_records_page_limit_metadata_bounds_and_corrupt_record_error_redaction(
    browser: Browser,
) -> None:
    runtime, _, client = browser

    # One canonical transaction for a realistically larger collection; no provider calls.
    def populate(db: sqlite3.Connection) -> None:
        db.executemany(
            "INSERT INTO memories(memory_id,owner_id,project_id,content,scope,sensitivity,"
            "retention,"
            "provenance,evidence_json,entity_version) VALUES (?,?,?,?,?,?,?,?,?,1)",
            [
                (
                    f"memory-bulk-{i}",
                    runtime.config.owner_id,
                    runtime.config.project_id,
                    "x" * 16384,
                    "dialogue",
                    "private",
                    "durable",
                    "owner",
                    "[]",
                )
                for i in range(250)
            ],
        )

    await runtime.repository.database.write(populate)
    _, page = await client._request_dict("GET", "/api/v1/memories?limit=100")
    assert len(page["memories"]) == 100 and page["total"] == 250 and page["next_cursor"]
    assert len(json.dumps(page)) < 130000
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE memories SET scope=?,provenance=? WHERE memory_id='memory-bulk-249'",
            ("s" * 200, "p" * 1000),
        )
    )
    _, detail = await client._request_dict("GET", "/api/v1/memories/memory-bulk-249")
    assert detail["memory"]["metadata_truncated"] and len(detail["memory"]["scope"]) == 128
    assert len(detail["memory"]["provenance"]) == 512
    await runtime.repository.database.write(
        lambda db: db.execute(
            "UPDATE memories SET valid_until='PRIVATE BAD DATE' WHERE memory_id='memory-bulk-249'",
        )
    )
    code, reply = await client._request_dict("GET", "/api/v1/memories/memory-bulk-249")
    assert code == 503 and "PRIVATE BAD DATE" not in json.dumps(reply)
