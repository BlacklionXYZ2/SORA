"""Tests for API protocol parsing, authentication, and security boundaries (P08.3)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sora.api import (
    ApiAuthenticationError,
    ApiForbiddenError,
    ApiSecurityError,
    ApiServerConfig,
    SecurityValidator,
    SoraApiClient,
    SoraApiServer,
    TokenAuthenticator,
    WebSocketProtocolError,
    WebSocketSession,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


class BufferWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self.closed = False

    def write(self, data: bytes | bytearray) -> None:
        self.data.extend(data)

    async def drain(self) -> None:
        return None

    def is_closing(self) -> bool:
        return self.closed

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


def test_api_server_config_enforces_loopback() -> None:
    # Valid loopback
    cfg = ApiServerConfig(host="127.0.0.1", port=8765, auth_token="supersecrettoken123")
    assert cfg.host == "127.0.0.1"

    # Non-loopback rejected when loopback_only=True
    with pytest.raises(ValueError, match="not a loopback address"):
        ApiServerConfig(host="192.168.1.100", loopback_only=True, auth_token="supersecrettoken123")

    # Short auth token rejected
    with pytest.raises(ValueError, match="at least 16 characters"):
        ApiServerConfig(host="127.0.0.1", auth_token="short")

    with pytest.raises(ValueError, match="does not accept prefix wildcards"):
        ApiServerConfig(
            auth_token="supersecrettoken123",
            allowed_origins=("http://localhost*",),
        )


def test_token_authenticator() -> None:
    auth = TokenAuthenticator("valid-token-123456789")

    # Missing header
    with pytest.raises(ApiAuthenticationError, match="Missing Authorization"):
        auth.authenticate(None)

    # Malformed scheme
    with pytest.raises(ApiAuthenticationError, match="Invalid Authorization scheme"):
        auth.authenticate("Basic dXNlcjpwYXNz")

    # Invalid token
    with pytest.raises(ApiAuthenticationError, match="Invalid Bearer authentication token"):
        auth.authenticate("Bearer wrong-token-123456789")

    # Valid token succeeds
    auth.authenticate("Bearer valid-token-123456789")


def test_security_validator_rejects_url_tokens() -> None:
    cfg = ApiServerConfig(auth_token="supersecrettoken123")
    sec = SecurityValidator(cfg)

    # Safe path
    sec.validate_request_path("/api/v1/tasks?limit=10&status=completed")

    # Forbidden token in query string (P08.3 invariant)
    with pytest.raises(ApiSecurityError, match="URL query strings are strictly forbidden"):
        sec.validate_request_path("/api/v1/tasks?token=supersecrettoken123")

    with pytest.raises(ApiSecurityError, match="URL query strings are strictly forbidden"):
        sec.validate_request_path("/api/v1/events/ws?access_token=secret")

    for key in ("TOKEN", "key", "bearer", "client-credential"):
        with pytest.raises(ApiSecurityError, match="URL query strings are strictly forbidden"):
            sec.validate_request_path(f"/api/v1/tasks?{key}=secret")


def test_security_validator_host_and_origin() -> None:
    cfg = ApiServerConfig(
        auth_token="supersecrettoken123",
        allowed_origins=("http://localhost", "http://127.0.0.1", "app://sora"),
    )
    sec = SecurityValidator(cfg)

    # Allowed hosts
    sec.validate_host("127.0.0.1:8765")
    sec.validate_host("localhost:8765")
    sec.validate_host("[::1]:8765")

    # Untrusted host
    with pytest.raises(ApiForbiddenError, match="not an authorized local loopback"):
        sec.validate_host("evil.com:8765")

    # Allowed origins
    sec.validate_origin("http://localhost:3000")
    sec.validate_origin("http://127.0.0.1:5173")
    sec.validate_origin("app://sora")

    # Untrusted origin
    with pytest.raises(ApiForbiddenError, match="not permitted by CORS"):
        sec.validate_origin("http://attacker.com")
    with pytest.raises(ApiForbiddenError, match="not permitted by CORS"):
        sec.validate_origin("http://localhost.evil.example")


@pytest.mark.asyncio
async def test_websocket_client_masks_frames_and_server_rejects_unmasked() -> None:
    client_writer = BufferWriter()
    client = WebSocketSession(
        asyncio.StreamReader(),
        client_writer,  # type: ignore[arg-type]
        "client",
        is_client=True,
    )
    await client.send_text("hello")
    assert client_writer.data[1] & 0x80

    server_reader = asyncio.StreamReader()
    server_reader.feed_data(bytes(client_writer.data))
    server_reader.feed_eof()
    server = WebSocketSession(
        server_reader,
        BufferWriter(),  # type: ignore[arg-type]
        "server",
    )
    assert await server.receive_text() == "hello"

    invalid_reader = asyncio.StreamReader()
    invalid_reader.feed_data(b"\x81\x05hello")
    invalid_reader.feed_eof()
    invalid_server = WebSocketSession(
        invalid_reader,
        BufferWriter(),  # type: ignore[arg-type]
        "invalid-server",
    )
    with pytest.raises(WebSocketProtocolError, match="must mask"):
        await invalid_server.receive_text()


@pytest.mark.asyncio
async def test_api_server_auth_enforcement_end_to_end(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()

    token = "test-token-abcdef-123456"
    api_cfg = ApiServerConfig(
        host="127.0.0.1",
        port=0,
        auth_token=token,
    )
    server = SoraApiServer(runtime, api_cfg)
    await server.start()

    try:
        # Unauthenticated request fails with 401
        unauthed_client = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token="",
        )
        status_resp = await unauthed_client.get_status()
        assert status_resp.get("error", {}).get("code") == "UNAUTHORIZED"

        # Wrong token fails with 401
        wrong_client = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token="wrong-token-abcdef-123456",
        )
        status_resp2 = await wrong_client.get_status()
        assert status_resp2.get("error", {}).get("code") == "UNAUTHORIZED"

        # Correct token succeeds with 200
        authed_client = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token=token,
        )
        status_resp3 = await authed_client.get_status()
        assert status_resp3.get("status") == "online"

        # Unauthenticated healthz check succeeds (liveness probe)
        health = await unauthed_client.get_health()
        assert health.get("status") == "ok"
    finally:
        await server.close()
        await runtime.close()
