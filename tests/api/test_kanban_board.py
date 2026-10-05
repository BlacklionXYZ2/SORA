"""P15.8: canonical plans, run attachment, mapping and retry through Core."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.models import TaskStatus
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_planned_card_never_runs_until_started_and_keeps_task_identity(
    tmp_path: Path,
) -> None:
    provider = DeterministicProvider(delay_seconds=0.05)
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=provider,
    )
    await runtime.start()
    server = SoraApiServer(
        runtime, ApiServerConfig(host="127.0.0.1", port=0, auth_token="board-token-test")
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token="board-token-test",
    )
    try:
        body = {"intent": "Repair the sample report", "idempotency_key": "plan-001"}
        status, planned = await client._request_dict("POST", "/api/v1/board/cards", body)
        assert status == 201
        assert planned["status"] == "planned"
        assert planned["run_started"] is False
        task_id = planned["task_id"]
        duplicate_status, duplicate = await client._request_dict(
            "POST", "/api/v1/board/cards", body
        )
        assert duplicate_status == 201
        assert duplicate["task_id"] == task_id
        conflict_status, _ = await client._request_dict(
            "POST", "/api/v1/board/cards",
            {"intent": "Different work", "idempotency_key": "plan-001"},
        )
        assert conflict_status == 409
        assert provider.start_count == 0
        assert await runtime.runtime_repository.list_runs(task_id) == []
        companion = await client.get_companion_projection()
        assert companion["background_workers_active"] == 0

        objects = await client.get_objects_projection()
        card = next(item for item in objects["cards"] if item["task_id"] == task_id)
        assert (card["column"], card["status"], card["run_count"]) == (
            "TODO", "planned", 0
        )
        assert card["intent"] == "Repair the sample report"
        assert card["referent_id"] == f"task:{task_id}"
        messages = await client.list_messages()
        assert any("No specialist has been started" in item["content"] for item in messages)

        missing_status, _ = await client._request_dict(
            "POST", f"/api/v1/board/cards/{task_id}/start",
            {"explicit_provider": "codex"},
        )
        assert missing_status == 409
        assert await runtime.runtime_repository.list_runs(task_id) == []

        started_status, started = await client._request_dict(
            "POST", f"/api/v1/board/cards/{task_id}/start", {}
        )
        assert started_status == 201
        assert started["task_id"] == task_id
        second_status, _ = await client._request_dict(
            "POST", f"/api/v1/board/cards/{task_id}/start", {}
        )
        assert second_status == 409
        assert len(await runtime.runtime_repository.list_runs(task_id)) == 1

        for _ in range(100):
            task = await runtime.runtime_repository.get_task(task_id)
            if task is not None and task.status is TaskStatus.COMPLETED:
                break
            await asyncio.sleep(0.02)
        assert task is not None and task.status is TaskStatus.COMPLETED
        objects = await client.get_objects_projection()
        card = next(item for item in objects["cards"] if item["task_id"] == task_id)
        assert (card["column"], card["status"], card["run_count"]) == (
            "DONE", "completed", 1
        )
        assert provider.start_count == 1
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_card_retry_keeps_previous_run_history(tmp_path: Path) -> None:
    provider = DeterministicProvider(fault=FaultMode.FAILURE)
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=provider,
    )
    await runtime.start()
    try:
        planned = await runtime.plan_task("Fix this later: failing fixture")
        task_id = planned.task_id
        await runtime.start_planned_task(task_id)
        for _ in range(100):
            task = await runtime.runtime_repository.get_task(task_id)
            if task is not None and task.status is TaskStatus.FAILED:
                break
            await asyncio.sleep(0.02)
        assert task is not None and task.status is TaskStatus.FAILED
        first = await runtime.runtime_repository.list_runs(task_id)
        assert len(first) == 1
        provider.fault = FaultMode.NONE
        retried = await runtime.retry(task_id)
        assert retried.task_id == task_id
        runs = await runtime.runtime_repository.list_runs(task_id)
        assert len(runs) == 2
        assert runs[0].run_id == first[0].run_id
        assert runs[1].attempt == 2
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_note_assignment_movement_and_removal_do_not_rewrite_task_history(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    server = SoraApiServer(
        runtime, ApiServerConfig(host="127.0.0.1", port=0, auth_token="board-edit-test-token")
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token="board-edit-test-token"
    )
    try:
        _, planned = await client._request_dict(
            "POST", "/api/v1/board/cards", {"intent": "Check the note board"}
        )
        task_id = planned["task_id"]
        path = f"/api/v1/board/cards/{task_id}"
        invalid, _ = await client._request_dict(
            "POST", path + "/assign", {"assigned_agent": "unknown"}
        )
        assert invalid == 400
        assigned, _ = await client._request_dict(
            "POST", path + "/assign", {"assigned_agent": "claude"}
        )
        stale, _ = await client._request_dict(
            "POST", path + "/move", {"column": "DONE", "expected_version": 0}
        )
        moved, _ = await client._request_dict(
            "POST", path + "/move", {"column": "DONE", "expected_version": 1}
        )
        assert stale == 409
        assert (assigned, moved) == (200, 200)
        objects = await client.get_objects_projection()
        card = next(item for item in objects["cards"] if item["task_id"] == task_id)
        assert (card["assigned_agent"], card["column"], card["column_source"]) == (
            "claude", "DONE", "manual"
        )
        assert (card["status"], card["run_count"]) == ("planned", 0)
        unchanged = await runtime.runtime_repository.get_task(task_id)
        assert unchanged is not None and unchanged.status is TaskStatus.PLANNED
        assert await runtime.runtime_repository.list_runs(task_id) == []
        removed, _ = await client._request_dict(
            "POST", path + "/remove", {"expected_version": 2}
        )
        assert removed == 200
        objects = await client.get_objects_projection()
        assert all(item["task_id"] != task_id for item in objects["cards"])
        assert await runtime.runtime_repository.get_task(task_id) is not None
        repeated, _ = await client._request_dict("POST", path + "/remove", {})
        assert repeated == 409

        def events(db: sqlite3.Connection) -> list[tuple[str, str]]:
            return [(row[0], row[1]) for row in db.execute(
                "SELECT action, actor FROM board_card_events WHERE task_id=? ORDER BY rowid",
                (task_id,),
            )]

        assert await runtime.repository.database.read(events) == [
            ("assign", "owner"), ("move", "owner"), ("remove", "owner")
        ]
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_sora_explicit_local_note_commands_and_remote_dialogue_boundary(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        added = await runtime.dialogue("Sora, add a note for Hermes: Review the sample")
        task_id = added.split("note ", 1)[1].split(" ", 1)[0]
        assert added.endswith("No agent run was started.")
        assert await runtime.runtime_repository.list_runs(task_id) == []
        moved = await runtime.dialogue(f"Sora, move note {task_id} to completed")
        assert "run status is unchanged" in moved
        def board_state(db: sqlite3.Connection) -> tuple[str, str, str]:
            row = db.execute(
                "SELECT column_name, assigned_agent, updated_by FROM board_cards WHERE task_id=?",
                (task_id,),
            ).fetchone()
            return row[0], row[1], row[2]
        assert await runtime.repository.database.read(board_state) == (
            "DONE", "hermes", "sora"
        )
        unchanged = await runtime.runtime_repository.get_task(task_id)
        assert unchanged is not None and unchanged.status is TaskStatus.PLANNED
        denied = await runtime.dialogue(
            f"Sora, remove note {task_id}", allow_board_actions=False
        )
        assert denied != (
            f"I removed note {task_id} from the board. Its task and run history remain."
        )
        assert await runtime.repository.database.read(board_state) == (
            "DONE", "hermes", "sora"
        )
        removed = await runtime.dialogue(f"Sora, remove note {task_id}")
        assert "task and run history remain" in removed
    finally:
        await runtime.close()
