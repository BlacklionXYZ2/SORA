"""Tests for companion, settings, object, and capability projections (P08.5)."""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_companion_and_settings_projections(tmp_path: Path) -> None:
    content_root = tmp_path / "content"
    content_root.mkdir()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            secrets=("super-secret-api-key", "db-password-12345"),
            content_roots=(content_root,),
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
        # Companion projection: dialogue state independent from background tasks
        comp_proj = await client.get_companion_projection()
        assert comp_proj["companion"]["name"] == "SORA"
        assert comp_proj["companion"]["dialogue_ready"] is True
        assert comp_proj["companion"]["state"] == "idle"
        _, controls = await client._request_dict("GET", "/api/v1/companion")
        assert controls["state"] == comp_proj["companion"]["state"]
        assert controls["renderer_state"] == "disconnected"
        assert comp_proj["companion"]["dialogue_model"] == "Offline test model"
        runtime.dialogue_in_progress = 1
        try:
            busy = await client.get_companion_projection()
            _, controls = await client._request_dict("GET", "/api/v1/companion")
            assert busy["companion"]["state"] == controls["state"] == "thinking"
            assert busy["companion"]["dialogue_ready"] is True
        finally:
            runtime.dialogue_in_progress = 0
        assert (await client.get_companion_projection())["companion"]["state"] == "idle"
        assert "specialists" in comp_proj
        assert "cody" in comp_proj["specialists"]
        assert "hermes" in comp_proj["specialists"]
        assert "antigravity" in comp_proj["specialists"]

        # Settings projection: secrets must be masked as ***REDACTED***
        settings_proj = await client.get_settings_projection()
        assert settings_proj["owner_id"] == runtime.config.owner_id
        for secret in settings_proj["secrets"]:
            assert secret == "***REDACTED***"
            assert "super-secret" not in secret
        assert settings_proj["context_max_chars"] == runtime.config.context_max_chars
        assert settings_proj["content_roots"] == [str(content_root.resolve())]

        content_status, content_projection = await client._request_dict(
            "GET", "/api/v1/content/references"
        )
        assert content_status == 200
        assert len(content_projection["references"]) == 1
        assert content_projection["references"][0]["kind"] == "repository"
        other_device = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token=token,
            device_id="another-device",
        )
        other_status, other_content = await other_device._request_dict(
            "GET", "/api/v1/content/references"
        )
        assert other_status == 200
        assert other_content["references"] == []

        await persist_operation_grant(
            runtime, "content.navigate:test-reference", grant_id="sensitive-grant-id"
        )
        status, permissions = await client._request_dict(
            "GET", "/api/v1/projections/permissions"
        )
        assert status == 200
        assert permissions["total"] == 1
        assert permissions["grants"][0]["resource"] == "content.navigate:test-reference"
        assert "sensitive-grant-id" not in str(permissions)
        assert "approval_id" not in str(permissions)

        # Desktop objects projection: Kanban tasks
        await client.submit_task("Kanban item 1")
        await client.submit_task("Kanban item 2")

        objects_proj = await client.get_objects_projection()
        assert objects_proj["type"] == "KanbanBoard"
        cards = objects_proj["cards"]
        assert len(cards) >= 2
        assert all("column" in c and "task_id" in c for c in cards)
        assert all(c["referent_id"] == f"task:{c['task_id']}" for c in cards)
        assert all("artifact_ids" in c for c in cards)

        # Capabilities projection: semantic verbs and active extensions
        caps_proj = await client.get_capabilities_projection()
        verbs = caps_proj["available_verbs"]
        assert "pause" in verbs
        assert "open" in verbs
        assert "delegate" in verbs
        assert caps_proj["active_extensions"] == []
        assert caps_proj["projection_revision"] >= 1

    finally:
        await server.close()
        await runtime.close()
