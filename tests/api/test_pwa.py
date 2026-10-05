"""P15.1 local PWA app-shell, cache safety, and replay convergence tests."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest, read_http_request
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


async def raw_request(port: int, path: str, *, token: str = "") -> HttpRequest:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    headers = [
        f"GET {path} HTTP/1.1\r\n",
        f"Host: 127.0.0.1:{port}\r\n",
        "Origin: http://127.0.0.1\r\n",
        "Connection: close\r\n",
    ]
    if token:
        headers.append(f"Authorization: Bearer {token}\r\n")
    headers.append("\r\n")
    writer.write("".join(headers).encode("ascii"))
    await writer.drain()
    response = await read_http_request(reader)
    writer.close()
    await writer.wait_closed()
    assert response is not None
    return response


@pytest.mark.asyncio
async def test_pwa_shell_is_public_but_api_is_authenticated_and_never_cacheable(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = "pwa-test-token-abcdef-123456"
    server = SoraApiServer(
        runtime,
        ApiServerConfig(host="127.0.0.1", port=0, auth_token=token),
    )
    await server.start()
    try:
        shell = await raw_request(server.actual_port, "/app")
        assert shell.path == "200"
        assert shell.header("Content-Type") == "text/html; charset=utf-8"
        assert "default-src 'self'" in (shell.header("Content-Security-Policy") or "")
        assert b"Connect privately" in shell.body
        assert b"bearer token" in shell.body

        service_worker = await raw_request(server.actual_port, "/service-worker.js")
        assert service_worker.path == "200"
        assert service_worker.header("Cache-Control") == "no-cache, no-store, must-revalidate"
        assert service_worker.header("Service-Worker-Allowed") == "/"

        unauthenticated = await raw_request(server.actual_port, "/api/v1/status")
        assert unauthenticated.path == "401"
        authenticated = await raw_request(server.actual_port, "/api/v1/status", token=token)
        assert authenticated.path == "200"
        assert authenticated.header("Cache-Control") == "no-store"
        assert authenticated.header("Pragma") == "no-cache"
        assert authenticated.header("Vary") == "Authorization, Origin"

        unknown_public_path = await raw_request(server.actual_port, "/app/../api-client.js")
        assert unknown_public_path.path == "401"
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_poll_replay_converges_after_disconnect_and_resyncs_ahead_cursor(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = "pwa-replay-token-abcdef-123456"
    server = SoraApiServer(
        runtime,
        ApiServerConfig(host="127.0.0.1", port=0, auth_token=token),
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token=token
    )
    try:
        await client.dialogue("first connected turn")
        first_page = await client.poll_events(0, limit=100)
        first_cursor = first_page["next_sequence"]
        assert first_cursor > 0
        assert first_page["resync_required"] is False
        invalid_limit = await client.poll_events(first_cursor, limit=501)
        assert invalid_limit["error"]["code"] == "INVALID_CURSOR"

        await client.dialogue("turn created while the PWA is disconnected")
        replay = await client.poll_events(first_cursor, limit=1)
        replayed_sequences = [event["sequence"] for event in replay["events"]]
        while replay["more_available"]:
            replay = await client.poll_events(replay["next_sequence"], limit=1)
            replayed_sequences.extend(event["sequence"] for event in replay["events"])
        assert replayed_sequences == list(range(first_cursor + 1, replay["latest_sequence"] + 1))

        ahead = await client.poll_events(replay["latest_sequence"] + 1000)
        assert ahead["resync_required"] is True
        assert ahead["reason"] == "cursor_ahead"
        assert ahead["next_sequence"] == replay["latest_sequence"]
        latest_contents = [
            message["content"] for message in ahead["snapshot"]["messages"][-2:]
        ]
        assert latest_contents == [
            "turn created while the PWA is disconnected",
            "SORA is available while background tasks run. You said: "
            "turn created while the PWA is disconnected",
        ]
    finally:
        await server.close()
        await runtime.close()
