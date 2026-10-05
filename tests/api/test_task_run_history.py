"""GUI-1c owner-local attempts: deterministic HTTP evidence, not native acceptance."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.contracts.content import ContentReference
from sora.contracts.models import NormalizedResult, TaskStatus
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.runtime.task_history import run_evidence

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


async def settled(runtime: SoraRuntime, task_id: str, status: TaskStatus) -> None:
    for _ in range(200):
        task = await runtime.runtime_repository.get_task(task_id)
        if task is not None and task.status is status:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Task did not settle as {status}")


@pytest.mark.asyncio
async def test_history_http_keeps_exact_old_results_and_task_bound_page_ceiling(
    tmp_path: Path,
) -> None:
    provider = DeterministicProvider(fault=FaultMode.FAILURE)
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT), provider=provider
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="run-history-test-token"))
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token="run-history-test-token"
    )
    try:
        planned = await runtime.plan_task("Inspect attempt history")
        task_id = planned.task_id
        path = f"/api/v1/tasks/{task_id}/runs"
        status, empty = await client._request_dict("GET", path)
        assert status == 200 and empty["runs"] == [] and empty["total"] == 0
        await runtime.start_planned_task(task_id)
        await settled(runtime, task_id, TaskStatus.FAILED)
        first = (await runtime.runtime_repository.list_runs(task_id))[0]
        provider.fault = FaultMode.NONE
        await runtime.retry(task_id)
        await settled(runtime, task_id, TaskStatus.COMPLETED)
        runs = await runtime.runtime_repository.list_runs(task_id)
        status, page = await client._request_dict("GET", path + "?limit=1")
        assert status == 200 and page["total"] == 2
        assert page["runs"][0]["run"]["run_id"] == runs[1].run_id
        cursor = page["next_cursor"]
        _, old = await client._request_dict("GET", path + f"/{first.run_id}")
        assert old["run"]["attempt"] == 1 and old["result"]["outcome"] == "failed"
        assert old["result"]["run_id"] == first.run_id
        _, current = await client._request_dict("GET", path + f"/{runs[1].run_id}")
        assert current["result"]["outcome"] == "completed"
        provider.fault = FaultMode.FAILURE
        await runtime.retry(task_id)
        await settled(runtime, task_id, TaskStatus.FAILED)
        _, older = await client._request_dict("GET", path + f"?limit=1&cursor={cursor}")
        assert older["total"] == 2 and older["next_cursor"] is None
        assert older["runs"][0]["run"]["run_id"] == first.run_id
        _, refreshed = await client._request_dict("GET", path)
        assert refreshed["total"] == 3 and len(refreshed["runs"]) == 3
        assert len({row["run"]["run_id"] for row in refreshed["runs"]}) == 3

        for query in ("limit=0", "limit=101", "limit=garbage", "cursor=bad!", "cursor="):
            code, reply = await client._request_dict("GET", path + "?" + query)
            assert code == 400 and reply["error"]["code"] == "INVALID_PAGE"
        forged = base64.urlsafe_b64encode(json.dumps(["task-other", 2, 1]).encode()).decode()
        code, _ = await client._request_dict("GET", path + "?cursor=" + forged)
        assert code == 400
        code, _ = await client._request_dict("GET", path + "/run-unknown")
        assert code == 404
        await runtime.repository.register_owner("owner-other")
        await runtime.repository.register_project("project-other", "owner-other")
        await runtime.repository.register_conversation(
            "conversation-other", "owner-other", "project-other"
        )
        other = await runtime.runtime_repository.submit(
            owner_id="owner-other",
            project_id="project-other",
            conversation_id="conversation-other",
            intent="Private other-owner task",
            idempotency_key="other-history",
            now=datetime.now(UTC),
            provider="deterministic",
        )
        for suffix in ("", f"/{first.run_id}"):
            code, _ = await client._request_dict(
                "GET", f"/api/v1/tasks/{other.task.task_id}/runs" + suffix
            )
            assert code == 404
            remote_reply = await server.routes.handle_request(
                HttpRequest("GET", path + suffix, {}, b""), remote_scopes=frozenset({"tasks.read"})
            )
            assert remote_reply.status_code == 403
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_report_projection_bounds_private_data_and_matches_only_exact_content(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime", identity_root=IDENTITY_ROOT, content_roots=(tmp_path,)
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        planned = await runtime.plan_task("Bounded evidence fixture")
        await runtime.start_planned_task(planned.task_id)
        await settled(runtime, planned.task_id, TaskStatus.COMPLETED)
        run = (await runtime.runtime_repository.list_runs(planned.task_id))[0]
        original = await runtime.runtime_repository.result_for_task(planned.task_id)
        assert original is not None
        path = tmp_path / "reported.txt"
        path.write_text("Synthetic registered content fixture\n", encoding="utf-8")
        report = NormalizedResult.model_validate(
            {
                **original.model_dump(),
                "summary": "Provider fixture report",
                "facts": ["PRIVATE-FACT"],
                "files_changed": [str(path), "relative.txt"],
                "commands_run": ["inert command"],
                "actions_taken": [f"Reported action {i}" for i in range(70)],
                "changelog_path": str(tmp_path / "report.md"),
            }
        )
        await runtime.repository.database.write(
            lambda db: db.execute(
                "UPDATE normalized_results SET payload=? WHERE result_id=?",
                (report.model_dump_json(), report.result_id),
            )
        )
        ref = ContentReference(
            reference_id="content-match",
            kind="file",
            label="Fixture",
            path=path,
            root=tmp_path,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
            created_at=datetime.now(UTC),
        )
        foreign = ref.model_copy(
            update={"reference_id": "content-foreign", "owner_id": "owner-other"}
        )
        data = await runtime.repository.database.read(
            lambda db: run_evidence(
                db, runtime.config.owner_id, planned.task_id, run.run_id, [ref, foreign]
            )
        )
        assert data.omitted_items == {"actions_taken": 6}
        assert "PRIVATE-FACT" not in data.model_dump_json()
        assert data.artifacts[0].reference_ids == ("content-match",)
        assert data.artifacts[1].reference_ids == () and data.artifacts[1].path == "relative.txt"
        assert (
            data.artifacts[2].kind == "reported changelog" and data.artifacts[2].reference_ids == ()
        )
        runtime.register_content_reference(ref)
        server = SoraApiServer(
            runtime, ApiServerConfig(port=0, auth_token="artifact-history-test-token")
        )
        await server.start()
        try:
            client = SoraApiClient(
                base_url=f"http://127.0.0.1:{server.actual_port}",
                auth_token="artifact-history-test-token",
            )
            route = f"/api/v1/tasks/{planned.task_id}/runs/{run.run_id}"
            status, wire = await client._request_dict("GET", route)
            assert status == 200 and wire["artifacts"][0]["reference_ids"] == ["content-match"]
            client.device_id = "device-other"
            _, other_device = await client._request_dict("GET", route)
            assert other_device["artifacts"][0]["reference_ids"] == []
        finally:
            await server.close()
        huge = NormalizedResult.model_validate(
            {
                **report.model_dump(),
                "summary": "x" * 16384,
                "conclusion": "y" * 16384,
                "changelog_entry": "z" * 1000,
            }
        )
        await runtime.repository.database.write(
            lambda db: db.execute(
                "UPDATE normalized_results SET payload=? WHERE result_id=?",
                (huge.model_dump_json(), huge.result_id),
            )
        )
        clipped = await runtime.repository.database.read(
            lambda db: run_evidence(db, runtime.config.owner_id, planned.task_id, run.run_id, [ref])
        )
        assert clipped.text_truncated and not clipped.artifacts
        assert clipped.omitted_items["files_changed"] == 2
        # A queued retry without a result must not use its task's previous result.
        retry = await runtime.runtime_repository.retry_task(
            planned.task_id, now=datetime.now(UTC), max_attempts=3
        )
        pending = await runtime.repository.database.read(
            lambda db: run_evidence(db, runtime.config.owner_id, planned.task_id, retry.run_id, [])
        )
        assert pending.result is None and pending.run.attempt == 2
    finally:
        await runtime.close()
