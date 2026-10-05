from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sora.contracts.models import ApprovalRequest, CapabilityGrant
from sora.persistence.database import SQLiteDatabase
from sora.persistence.migrations import CURRENT_SCHEMA_VERSION
from sora.persistence.repository import SoraRepository
from tests.contracts.helpers import example_text

from .helpers import sample_message, sample_run, sample_session, sample_task


@pytest.mark.asyncio
async def test_restart_preserves_task_run_session_and_atomic_outbox(tmp_path: Path) -> None:
    path = tmp_path / "sora.db"
    database = SQLiteDatabase(path)
    await database.initialize()
    repository = SoraRepository(database)
    await repository.register_owner("owner-local")
    await repository.register_project("project-sora", "owner-local")
    await repository.register_conversation("conversation-001", "owner-local", "project-sora")
    await repository.append_message(sample_message())
    await repository.create_task(sample_task())
    await repository.create_run(sample_run())
    await repository.create_session(sample_session())
    approval = ApprovalRequest.model_validate_json(example_text("valid", "approval-request.json"))
    grant = CapabilityGrant.model_validate_json(example_text("valid", "capability-grant.json"))
    await repository.save_approval(approval)
    await repository.save_grant(grant)

    reopened = SQLiteDatabase(path)
    await reopened.initialize()
    restored = SoraRepository(reopened)

    assert await restored.get_task("task-001") == sample_task()
    assert await restored.list_messages("conversation-001") == [sample_message()]
    assert await restored.get_grant("grant-read") == grant
    assert await restored.counts() == {
        "messages": 1,
        "tasks": 1,
        "agent_runs": 1,
        "agent_sessions": 1,
        "facts": 0,
        "memories": 0,
        "normalized_results": 0,
        "approvals": 1,
        "grants": 1,
        "events": 9,
        "outbox": 9,
    }
    assert await restored.revision() == 9


@pytest.mark.asyncio
async def test_previous_schema_fixture_migrates_forward(tmp_path: Path) -> None:
    path = tmp_path / "previous.db"
    previous = SQLiteDatabase(path)
    await previous.initialize(target_version=1)
    assert await previous.schema_version() == 1

    current = SQLiteDatabase(path)
    await current.initialize()

    def outbox_columns(connection: sqlite3.Connection) -> set[str]:
        return {str(row[1]) for row in connection.execute("PRAGMA table_info(outbox)")}

    def action_columns(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(desktop_action_attempts)")
        }

    assert await current.schema_version() == CURRENT_SCHEMA_VERSION == 12
    assert "delivered_at" in await current.read(outbox_columns)
    assert {"attempt_id", "request_hash", "status", "payload"} <= await current.read(
        action_columns
    )

    def remote_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%remote%' "
                "OR name IN ('paired_devices', 'pairing_invitations')"
            )
        }

    assert {
        "pairing_invitations",
        "paired_devices",
        "remote_sessions",
        "remote_access_audit",
    } <= await current.read(remote_tables)
