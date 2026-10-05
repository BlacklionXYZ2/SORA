"""GUI-1d control metadata/worker actions; no physical microphone/model acceptance."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.voice.client import AudioFrame
from sora.voice.windows_bridge import WindowsVoiceBridge
from sora.voice.windows_worker import AudioWorker

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_output_only_worker_action_preserves_capture_and_response_task() -> None:
    worker = AudioWorker()
    client = SimpleNamespace(stop_speaking=AsyncMock())
    worker.client = client  # type: ignore[assignment]
    worker.recording = True
    worker.generation = 7
    worker.frames = [AudioFrame(0, datetime.now(UTC), b"\0" * 3200)]
    response = asyncio.create_task(asyncio.sleep(60))
    worker.response_task = response
    try:
        await worker.stop_output()
        client.stop_speaking.assert_awaited_once_with(cancel_generation=False)
        assert worker.recording and worker.generation == 7 and len(worker.frames) == 1
        assert not response.done() and not response.cancelled()
    finally:
        response.cancel()
        await asyncio.gather(response, return_exceptions=True)


def test_abort_failure_still_closes_capture_and_reports_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    worker = AudioWorker()
    calls: list[str] = []
    metadata: list[dict[str, Any]] = []

    def abort() -> None:
        calls.append("abort")
        raise OSError("Synthetic device loss")

    worker.recording = True
    worker.stream = SimpleNamespace(abort=abort, close=lambda: calls.append("close"))
    monkeypatch.setattr("sora.voice.windows_worker.emit", lambda **data: metadata.append(data))
    with pytest.raises(OSError, match="device loss"):
        worker.stop_capture()
    assert calls == ["abort", "close"] and not worker.recording and worker.stream is None
    assert metadata == [{"microphone_open": False}]


@pytest.mark.asyncio
async def test_worker_capture_metadata_is_independent_of_general_state() -> None:
    bridge = WindowsVoiceBridge()
    release = asyncio.Event()
    first = True

    async def readline() -> bytes:
        nonlocal first
        if first:
            first = False
            return b'{"state":"thinking","message":"fixture","microphone_open":true}\n'
        await release.wait()
        return b""

    process = SimpleNamespace(returncode=None, stdout=SimpleNamespace(readline=readline))

    async def wait() -> int:
        process.returncode = 0
        return 0

    process.wait = wait
    bridge.process = process  # type: ignore[assignment]
    task = asyncio.create_task(bridge._read(process))  # type: ignore[arg-type]
    try:
        for _ in range(50):
            if bridge.microphone_open is True:
                break
            await asyncio.sleep(0)
        assert bridge.status()["state"] == "thinking" and bridge.status()["microphone_open"] is True
    finally:
        release.set()
        await task
    assert bridge.status()["microphone_open"] is False


@pytest.mark.asyncio
async def test_local_output_only_http_action_obeys_static_policy_and_remote_boundary(
    tmp_path: Path,
) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(
        SettingsEdit(
            version=settings.active.version,
            expected_revision=settings.active.revision,
            changes={"local_companion.voice": True},
        )
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="voice-gui-control-fixture"))
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token="voice-gui-control-fixture"
    )
    runtime.local_voice.command = AsyncMock(return_value={})  # type: ignore[method-assign]
    try:
        status, wire = await client._request_dict("GET", "/api/v1/voice/local")
        assert status == 200 and wire["microphone_open"] is False and wire["enabled"] is True
        assert not wire["running"] and wire["state"] == "stopped"
        status, reply = await client._request_dict(
            "POST", "/api/v1/voice/local", {"action": "stop_output"}
        )
        assert status == 200 and reply["enabled"] is True and reply["microphone_open"] is False
        runtime.local_voice.command.assert_awaited_once_with("stop_output")
        with owner_local_scope():
            response = await server.routes.handle_request(
                HttpRequest("POST", "/api/v1/voice/local", {}, b'{"action":"stop_output"}'),
                remote_scopes=frozenset({"conversation:write"}),
            )
            assert response.status_code == 403
        settings.save(
            SettingsEdit(
                version=settings.active.version,
                expected_revision=settings.active.revision,
                changes={"local_companion.voice": False},
            )
        )
        status, reply = await client._request_dict(
            "POST", "/api/v1/voice/local", {"action": "stop_output"}
        )
        assert status == 403 and reply["error"]["code"] == "FORBIDDEN"
        runtime.local_voice.command.assert_awaited_once()
        status, _ = await client._request_dict(
            "POST", "/api/v1/voice/local", {"action": "arbitrary"}
        )
        assert status == 400
        status, closed = await client._request_dict(
            "POST", "/api/v1/voice/local", {"action": "close"}
        )
        assert status == 200 and closed["enabled"] is False
        assert runtime.local_voice.process is None
        # No worker/model/agent was started by reading or controlling this isolated fixture.
        assert not await runtime.runtime_repository.list_tasks()
    finally:
        await server.close()
        await runtime.close()
