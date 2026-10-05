"""Owner-local validated runtime settings and restart activation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.remote import required_remote_scope
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.runtime.settings import RuntimeSettingsUpdate

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_settings_are_validated_staged_redacted_and_activated_on_restart(
    tmp_path: Path,
) -> None:
    root = tmp_path / "runtime"
    initial = SoraRuntime(
        RuntimeConfig(root=root, identity_root=IDENTITY_ROOT,
                      dialogue_api_key=SecretStr("private-settings-sentinel")),
        provider=DeterministicProvider(),
    )
    await initial.start()
    server = SoraApiServer(
        initial, ApiServerConfig(host="127.0.0.1", port=0,
                                 auth_token="settings-initial-token")
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token="settings-initial-token",
    )
    request = {
        "version": 1, "expected_revision": 0,
        "dialogue_backend": "openai-compatible", "dialogue_model": "local-test-model",
        "dialogue_base_url": "http://127.0.0.1:1234/v1",
        "dialogue_timeout_seconds": 20, "worker_count": 3,
        "context_max_chars": 12000,
    }
    try:
        status, before = await client._request_dict(
            "GET", "/api/v1/projections/settings"
        )
        assert status == 200
        assert before["settings_revision"] == 0
        assert before["restart_required"] is False
        assert before["dialogue_api_key_configured"] is True
        assert "private-settings-sentinel" not in str(before)
        bad_status, _ = await client._request_dict(
            "POST", "/api/v1/settings", {**request,
                "dialogue_base_url": "https://user:secret@example.com/v1"},
        )
        assert bad_status == 400
        missing_version, _ = await client._request_dict(
            "POST", "/api/v1/settings", {key: value for key, value in request.items()
                                         if key != "version"},
        )
        assert missing_version == 400
        secret_status, _ = await client._request_dict(
            "POST", "/api/v1/settings", {**request, "dialogue_api_key": "not-allowed"},
        )
        assert secret_status == 400
        status, saved = await client._request_dict("POST", "/api/v1/settings", request)
        assert status == 200
        assert saved == {"settings_revision": 1, "restart_required": True}
        stale_status, _ = await client._request_dict("POST", "/api/v1/settings", request)
        assert stale_status == 409
        _, staged = await client._request_dict("GET", "/api/v1/projections/settings")
        assert staged["dialogue_backend"] == "deterministic"
        assert staged["worker_count"] == 2
        assert staged["pending_settings"]["dialogue_model"] == "local-test-model"
        assert staged["settings_revision"] == 1
        assert staged["active_settings_revision"] == 0
        saved_file = root / "data" / "runtime-settings.json"
        content = saved_file.read_text(encoding="utf-8")
        assert "private-settings-sentinel" not in content
        assert "dialogue_api_key" not in content
    finally:
        await server.close()
        await initial.close()

    restarted = SoraRuntime(
        RuntimeConfig(root=root, identity_root=IDENTITY_ROOT,
                      dialogue_api_key=SecretStr("private-settings-sentinel")),
        provider=DeterministicProvider(),
    )
    await restarted.start()
    try:
        assert restarted.config.dialogue_backend == "openai-compatible"
        assert restarted.config.dialogue_model == "local-test-model"
        assert restarted.config.worker_count == 3
        assert restarted.config.context_max_chars == 12000
        assert restarted.runtime_settings_view() == {
            "settings_revision": 1, "active_settings_revision": 1,
            "restart_required": False, "pending_settings": None,
        }
    finally:
        await restarted.close()


def test_settings_write_is_absent_from_remote_surface() -> None:
    assert required_remote_scope("POST", "/api/v1/settings") is None
    assert required_remote_scope("GET", "/api/v1/projections/settings") is None


@pytest.mark.asyncio
async def test_saving_startup_defaults_creates_a_durable_revision(tmp_path: Path) -> None:
    root = tmp_path / "defaults"
    runtime = SoraRuntime(RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider())
    await runtime.start()
    try:
        request = RuntimeSettingsUpdate.model_validate({
                "version": 1, "expected_revision": 0,
                "dialogue_backend": "deterministic", "dialogue_model": None,
                "dialogue_base_url": None, "dialogue_timeout_seconds": 30,
                "worker_count": 2, "context_max_chars": 8000,
            })
        revision = await runtime.stage_runtime_settings(request)
        assert revision == 1
        assert (root / "data" / "runtime-settings.json").exists()
        assert runtime.runtime_settings_view()["restart_required"] is True
        assert await runtime.stage_runtime_settings(
            request.model_copy(update={"expected_revision": 1})
        ) == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_real_core_restart_keeps_shared_surface_state_and_rotates_owner_token(
    tmp_path: Path,
) -> None:
    root = tmp_path / "restart-state"
    config = RuntimeConfig(root=root, identity_root=IDENTITY_ROOT)
    first = SoraRuntime(config, provider=DeterministicProvider())
    await first.start()
    server = SoraApiServer(first, ApiServerConfig(host="127.0.0.1", port=0,
                                                  auth_token="first-restart-token"))
    await server.start()
    first_client = SoraApiClient(base_url=f"http://127.0.0.1:{server.actual_port}",
                                 auth_token="first-restart-token")
    try:
        dialogue_status, _ = await first_client._request_dict(
            "POST", "/api/v1/dialogue", {"content": "Remember the restart check"}
        )
        assert dialogue_status == 201
        plan_status, planned = await first_client._request_dict(
            "POST", "/api/v1/board/cards",
            {"intent": "Check surface parity", "idempotency_key": "restart-parity-card"},
        )
        assert plan_status == 201
        task_id = planned["task_id"]
        status, old_messages = await first_client._request_list(
            "GET", "/api/v1/messages?limit=100"
        )
        assert status == 200 and len(old_messages) >= 2
        status, old_board = await first_client._request_dict(
            "GET", "/api/v1/projections/objects"
        )
        assert status == 200 and old_board["cards"][0]["task_id"] == task_id
        status, saved = await first_client._request_dict("POST", "/api/v1/settings", {
            "version": 1, "expected_revision": 0, "dialogue_backend": "deterministic",
            "dialogue_model": None, "dialogue_base_url": None,
            "dialogue_timeout_seconds": 15, "worker_count": 3,
            "context_max_chars": 12000,
        })
        assert status == 200 and saved["restart_required"] is True
        status, pre_restart = await first_client._request_dict(
            "GET", "/api/v1/projections/settings"
        )
        assert status == 200 and pre_restart["worker_count"] == 2
    finally:
        await server.close()
        await first.close()

    restarted = SoraRuntime(config, provider=DeterministicProvider())
    await restarted.start()
    new_server = SoraApiServer(restarted, ApiServerConfig(host="127.0.0.1", port=0,
                                                           auth_token="second-restart-token"))
    await new_server.start()
    origin = f"http://127.0.0.1:{new_server.actual_port}"
    widget = SoraApiClient(base_url=origin, auth_token="second-restart-token")
    full_app = SoraApiClient(base_url=origin, auth_token="second-restart-token")
    pwa = SoraApiClient(base_url=origin, auth_token="second-restart-token")
    avatar = SoraApiClient(base_url=origin, auth_token="second-restart-token")
    old_token = SoraApiClient(base_url=origin, auth_token="first-restart-token")
    try:
        assert (await old_token._request_dict("GET", "/api/v1/status"))[0] == 401
        _, widget_messages = await widget._request_list("GET", "/api/v1/messages?limit=100")
        _, widget_tasks = await widget._request_dict("GET", "/api/v1/tasks?limit=100&offset=0")
        _, full_messages = await full_app._request_list("GET", "/api/v1/messages?limit=100")
        _, full_board = await full_app._request_dict("GET", "/api/v1/projections/objects")
        _, pwa_messages = await pwa._request_list("GET", "/api/v1/messages?limit=100")
        _, pwa_board = await pwa._request_dict("GET", "/api/v1/projections/objects")
        _, embodiment = await avatar._request_dict("GET", "/api/v1/projections/embodiment")
        _, companion = await avatar._request_dict("GET", "/api/v1/projections/companion")
        _, settings = await full_app._request_dict("GET", "/api/v1/projections/settings")
        expected_messages = [message["message_id"] for message in old_messages]
        assert [message["message_id"] for message in widget_messages] == expected_messages
        assert [message["message_id"] for message in full_messages] == expected_messages
        assert [message["message_id"] for message in pwa_messages] == expected_messages
        assert [task["task_id"] for task in widget_tasks["tasks"]] == [task_id]
        assert full_board["cards"][0]["task_id"] == task_id
        assert pwa_board["cards"][0]["task_id"] == task_id
        assert embodiment["revision"] >= 0
        assert companion["companion"]["dialogue_ready"] is True
        assert settings["worker_count"] == 3
        assert settings["context_max_chars"] == 12000
        assert settings["settings_revision"] == settings["active_settings_revision"] == 1
        assert settings["restart_required"] is False
    finally:
        await new_server.close()
        await restarted.close()
