"""Tests for Core REST endpoints, task submission, messages, and workspaces (P08.1)."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


def committed_repository(tmp_path: Path) -> Path:
    repository = tmp_path / "source"
    repository.mkdir(parents=True, exist_ok=True)
    git(repository, "init")
    git(repository, "config", "user.email", "sora-tests@example.invalid")
    git(repository, "config", "user.name", "SORA Tests")
    (repository / "target.txt").write_text("initial base\n", encoding="utf-8")
    git(repository, "add", "target.txt")
    git(repository, "commit", "-m", "initial base")
    return repository


@pytest.mark.asyncio
async def test_api_task_crud_and_idempotency(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
        ),
        provider=DeterministicProvider(delay_seconds=0.5),
    )
    await runtime.start()

    token = "test-token-abcdef-123456"
    api_cfg = ApiServerConfig(host="127.0.0.1", port=0, auth_token=token)
    server = SoraApiServer(runtime, api_cfg)
    await server.start()

    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token=token,
    )

    try:
        # Submit a task
        idemp_key = "idemp-test-123"
        task_data = await client.submit_task(
            "Research optimization strategies",
            idempotency_key=idemp_key,
        )
        task_id = task_data["task_id"]
        assert task_id.startswith("task-")

        # Idempotency check: submitting again with same key returns identical task
        task_data2 = await client.submit_task(
            "Research optimization strategies",
            idempotency_key=idemp_key,
        )
        assert task_data2["task_id"] == task_id

        # Get task report
        report = await client.get_task(task_id)
        assert report["task_id"] == task_id

        # List tasks with pagination
        task_list = await client.list_tasks(limit=10, offset=0)
        assert any(t["task_id"] == task_id for t in task_list["tasks"])

        await runtime.repository.register_owner("owner-other")
        await runtime.repository.register_project("project-other", "owner-other")
        await runtime.repository.register_conversation(
            "conversation-other", "owner-other", "project-other"
        )
        other = await runtime.runtime_repository.submit(
            owner_id="owner-other",
            project_id="project-other",
            conversation_id="conversation-other",
            intent="private task for another owner",
            idempotency_key="other-owner-task",
            now=datetime.now(UTC),
            provider="deterministic",
        )
        scoped_list = await client.list_tasks(limit=100)
        assert all(item["task_id"] != other.task.task_id for item in scoped_list["tasks"])
        hidden = await client.get_task(other.task.task_id)
        assert hidden["error"]["code"] == "NOT_FOUND"
        invalid_page = await client.list_tasks(limit=-1, offset=0)
        assert invalid_page["error"]["code"] == "INVALID_PAGE"

        # Cancel task
        cancel_resp = await client.cancel_task(task_id)
        assert cancel_resp.get("cancelled") is True

    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_api_messages_and_workspaces_workflow(tmp_path: Path) -> None:
    repo = committed_repository(tmp_path)
    ws_state = tmp_path / "ws-state"

    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            coding_repository_root=repo,
            coding_workspace_root=ws_state,
            coding_base_ref="HEAD",
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()

    token = "test-token-abcdef-123456"
    api_cfg = ApiServerConfig(host="127.0.0.1", port=0, auth_token=token)
    server = SoraApiServer(runtime, api_cfg)
    await server.start()

    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token=token,
    )

    try:
        # Messages endpoint
        post_resp = await client.post_message("Hello SORA companion!")
        assert "revision" in post_resp

        messages = await client.list_messages(limit=10)
        assert len(messages) >= 1
        assert any("Hello SORA companion!" in m["content"] for m in messages)

        # Allocate a workspace directly for testing API workspace endpoints
        assert runtime.git_workspace_manager is not None
        task_data = await client.submit_task("Prepare isolated API workspace")
        ws_rec = runtime.git_workspace_manager.allocate(
            repo,
            workspace_id="ws-api-test",
            task_id=task_data["task_id"],
            base_ref="HEAD",
            lease_owner="worker-1",
            lease_seconds=60,
        )
        (ws_rec.worktree_path / "target.txt").write_text("modified by agent\n", encoding="utf-8")

        # List workspaces
        ws_list = await client.list_workspaces()
        assert any(w["workspace_id"] == "ws-api-test" for w in ws_list["workspaces"])

        # Diff workspace
        diff_resp = await client.diff_workspace("ws-api-test")
        assert "modified by agent" in diff_resp["diff"]

        # Validate workspace commands
        await persist_operation_grant(
            runtime,
            "workspace.validate:ws-api-test",
            grant_id="grant-api-validate",
        )
        val_resp = await client.validate_workspace(
            "ws-api-test", ["git status"], grant_id="grant-api-validate"
        )
        assert val_resp.get("success") is True

        # Gated integration: an unknown grant fails closed.
        unauth_int = await client.integrate_workspace(
            "ws-api-test", grant_id="grant-does-not-exist"
        )
        assert unauth_int.get("error", {}).get("code") == "AUTHORIZATION_REQUIRED"

        # Legacy callers cannot self-assert an approver in the request payload.
        _, self_asserted = await client._request_dict(
            "POST",
            "/api/v1/workspaces/ws-api-test/integrate",
            body={"authorized_by": "attacker", "commit_message": "bypass attempt"},
        )
        assert self_asserted.get("error", {}).get("code") == "AUTHORIZATION_REQUIRED"

        # A persisted, approved, exact-scope grant succeeds; identity text is not client supplied.
        await persist_operation_grant(
            runtime,
            "workspace.integrate:ws-api-test",
            grant_id="grant-api-integrate",
            actor_id="operator-alice",
        )
        int_resp = await client.integrate_workspace(
            "ws-api-test",
            grant_id="grant-api-integrate",
            commit_message="Apply agent changes",
        )
        int_id = int_resp["integration_id"]
        assert int_resp["status"] == "integrated"

        # Rollback integration
        await persist_operation_grant(
            runtime,
            f"integration.rollback:{int_id}",
            grant_id="grant-api-rollback",
            actor_id="operator-alice",
        )
        rb_resp = await client.rollback_integration(int_id, grant_id="grant-api-rollback")
        assert rb_resp["status"] == "rolled_back"

    finally:
        await server.close()
        await runtime.close()
