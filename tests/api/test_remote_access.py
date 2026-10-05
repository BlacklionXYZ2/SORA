"""P15.2 TLS remote pairing, scoped session, revocation, limit, and audit acceptance."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest, read_http_request
from sora.api.remote import RemoteAccessError, RemoteAccessManager
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"
TLS_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "tls"
TEST_CERTIFICATE = TLS_ROOT / "localhost-test-cert.pem"
TEST_PRIVATE_KEY = TLS_ROOT / "localhost-test-key.pem"


def unverified_test_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def remote_config(token: str, remote_port: int, *, pairing_limit: int = 5) -> ApiServerConfig:
    return ApiServerConfig(
        host="127.0.0.1",
        port=0,
        auth_token=token,
        remote_access_enabled=True,
        remote_host="127.0.0.1",
        remote_port=remote_port,
        remote_tls_certificate_file=TEST_CERTIFICATE,
        remote_tls_private_key_file=TEST_PRIVATE_KEY,
        remote_allowed_origins=(f"https://127.0.0.1:{remote_port}",),
        pairing_attempt_limit=pairing_limit,
    )


async def raw_tls_get(
    port: int,
    path: str,
    *,
    origin: str,
    device_id: str = "phone-raw-0001",
    authorization: str | None = None,
) -> HttpRequest:
    reader, writer = await asyncio.open_connection(
        "127.0.0.1",
        port,
        ssl=unverified_test_context(),
        server_hostname="127.0.0.1",
    )
    authorization_header = f"Authorization: {authorization}\r\n" if authorization else ""
    writer.write(
        (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: 127.0.0.1:{port}\r\n"
            f"Origin: {origin}\r\n"
            f"X-SORA-Device-ID: {device_id}\r\n"
            f"{authorization_header}"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
    )
    await writer.drain()
    response = await read_http_request(reader)
    writer.close()
    await writer.wait_closed()
    assert response is not None
    return response


def test_remote_configuration_fails_closed() -> None:
    token = "remote-config-token-abcdef-123456"
    with pytest.raises(ValueError, match="remote_host"):
        ApiServerConfig(auth_token=token, remote_access_enabled=True)
    with pytest.raises(ValueError, match="loopback-only"):
        ApiServerConfig(
            host="0.0.0.0", loopback_only=False, auth_token=token
        )
    with pytest.raises(ValueError, match="concrete"):
        ApiServerConfig(
            auth_token=token,
            remote_access_enabled=True,
            remote_host="0.0.0.0",
            remote_tls_certificate_file=TEST_CERTIFICATE,
            remote_tls_private_key_file=TEST_PRIVATE_KEY,
            remote_allowed_origins=("https://sora.test",),
        )
    with pytest.raises(ValueError, match="concrete"):
        ApiServerConfig(
            auth_token=token,
            remote_access_enabled=True,
            remote_host="8.8.8.8",
            remote_tls_certificate_file=TEST_CERTIFICATE,
            remote_tls_private_key_file=TEST_PRIVATE_KEY,
            remote_allowed_origins=("https://sora.test",),
        )
    with pytest.raises(ValueError, match="HTTPS"):
        ApiServerConfig(
            auth_token=token,
            remote_access_enabled=True,
            remote_host="127.0.0.1",
            remote_tls_certificate_file=TEST_CERTIFICATE,
            remote_tls_private_key_file=TEST_PRIVATE_KEY,
            remote_allowed_origins=("http://127.0.0.1:8766",),
        )
    with pytest.raises(ValueError, match="require remote_access_enabled"):
        ApiServerConfig(auth_token=token, remote_host="127.0.0.1")


@pytest.mark.asyncio
async def test_paired_remote_session_is_scoped_revocable_and_audited(
    tmp_path: Path, unused_tcp_port: int
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = "remote-owner-token-abcdef-123456"
    config = remote_config(token, unused_tcp_port, pairing_limit=6)
    server = SoraApiServer(runtime, config)
    await server.start()
    assert server.actual_remote_port == unused_tcp_port

    local = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token=token,
    )
    remote_origin = f"https://127.0.0.1:{unused_tcp_port}"
    device_id = "phone-fixture-0001"
    remote = SoraApiClient(
        base_url=remote_origin,
        origin=remote_origin,
        device_id=device_id,
        ssl_context=unverified_test_context(),
    )
    try:
        await local.dialogue("canonical message before pairing")

        # Merely reaching the private TLS listener grants no API authority. The owner
        # bearer is also refused there; it belongs only on the loopback listener.
        unpaired = await remote._request_dict("GET", "/api/v1/messages")
        assert unpaired[1]["error"]["code"] == "REMOTE_UNAUTHORIZED"
        unpaired_raw = await raw_tls_get(
            unused_tcp_port, "/api/v1/messages", origin=remote_origin
        )
        assert unpaired_raw.path == "401"
        assert unpaired_raw.header("Access-Control-Allow-Origin") == remote_origin
        assert unpaired_raw.header("Cache-Control") == "no-store"
        assert unpaired_raw.header("WWW-Authenticate") == 'SoraSession realm="SORA Core"'
        leaked_owner = SoraApiClient(
            base_url=remote_origin,
            auth_token=token,
            origin=remote_origin,
            device_id=device_id,
            ssl_context=unverified_test_context(),
        )
        owner_attempt = await leaked_owner._request_dict("GET", "/api/v1/messages")
        assert owner_attempt[1]["error"]["code"] == "REMOTE_UNAUTHORIZED"
        readiness = await remote._request_dict("GET", "/readyz")
        assert readiness[1]["error"]["code"] == "REMOTE_UNAUTHORIZED"
        health = await remote.get_health()
        assert health["status"] == "ok"
        websocket = await leaked_owner._request_dict(
            "GET",
            "/api/v1/events/ws",
            headers={
                "Connection": "Upgrade",
                "Upgrade": "websocket",
                "Sec-WebSocket-Version": "13",
                "Sec-WebSocket-Key": "MDEyMzQ1Njc4OWFiY2RlZg==",
            },
        )
        assert websocket[1]["error"]["code"] == "REMOTE_WEBSOCKET_UNAVAILABLE"
        wrong_origin = SoraApiClient(
            base_url=remote_origin,
            origin="https://evil.example",
            device_id=device_id,
            ssl_context=unverified_test_context(),
        )
        origin_denied = await wrong_origin._request_dict("GET", "/healthz")
        assert origin_denied[1]["error"]["code"] == "FORBIDDEN_ORIGIN"
        host_denied = await remote._request_dict(
            "GET", "/healthz", headers={"Host": "evil.example"}
        )
        assert host_denied[1]["error"]["code"] == "FORBIDDEN_ORIGIN"
        plaintext = SoraApiClient(
            base_url=f"http://127.0.0.1:{unused_tcp_port}",
            origin=remote_origin,
            device_id=device_id,
        )
        with pytest.raises((ConnectionError, OSError)):
            await plaintext.get_health()

        invitation = await local.create_pairing_invitation(
            "Acceptance phone",
            scopes=[
                "conversation:read",
                "tasks:read",
                "events:read",
                "projections:read",
            ],
            expires_in_seconds=120,
        )
        assert invitation["pairing_code"]
        claimed = await remote.claim_pairing(
            invitation["pairing_code"], device_id=device_id, label="Acceptance phone"
        )
        assert claimed["device_id"] == device_id

        reused = await remote.claim_pairing(
            invitation["pairing_code"],
            device_id="phone-fixture-0002",
            label="Replay phone",
        )
        assert reused["error"]["code"] == "PAIRING_USED"

        escalated = await remote.create_remote_session(
            claimed["device_credential"],
            device_id=device_id,
            scopes=["conversation:write"],
        )
        assert escalated["error"]["code"] == "SCOPE_ESCALATION"
        session = await remote.create_remote_session(
            claimed["device_credential"], device_id=device_id
        )
        assert session["session_token"]

        paired = SoraApiClient(
            base_url=remote_origin,
            auth_token=session["session_token"],
            authorization_scheme="SoraSession",
            origin=remote_origin,
            device_id=device_id,
            ssl_context=unverified_test_context(),
        )
        messages = await paired.list_messages()
        assert any(item["content"] == "canonical message before pairing" for item in messages)
        paired_readiness = await raw_tls_get(
            unused_tcp_port,
            "/readyz",
            origin=remote_origin,
            device_id=device_id,
            authorization=f"SoraSession {session['session_token']}",
        )
        assert paired_readiness.path == "200"
        assert paired_readiness.header("Cache-Control") == "no-store"
        denied_dialogue = await paired.dialogue("scope escalation through a route")
        assert denied_dialogue["error"]["code"] == "REMOTE_SCOPE_DENIED"
        denied_extension = await paired._request_dict("GET", "/api/v1/extensions")
        assert denied_extension[1]["error"]["code"] == "REMOTE_SCOPE_DENIED"
        denied_settings = await paired._request_dict(
            "GET", "/api/v1/projections/settings"
        )
        assert denied_settings[1]["error"]["code"] == "REMOTE_SCOPE_DENIED"
        denied_permissions = await paired._request_dict(
            "GET", "/api/v1/projections/permissions"
        )
        assert denied_permissions[1]["error"]["code"] == "REMOTE_SCOPE_DENIED"
        denied_content = await paired._request_dict(
            "GET", "/api/v1/content/references"
        )
        assert denied_content[1]["error"]["code"] == "REMOTE_SCOPE_DENIED"
        events = await paired.poll_events(0)
        assert events["snapshot"] is None
        assert all(
            set(event) <= {"sequence", "timestamp", "event_type", "revision"}
            for event in events["events"]
        )

        def expire_session(db: sqlite3.Connection) -> None:
            db.execute(
                "UPDATE remote_sessions SET expires_at=? WHERE session_id=?",
                (
                    (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                    session["session_id"],
                ),
            )

        await runtime.repository.database.write(expire_session)
        expired = await paired._request_dict("GET", "/api/v1/messages")
        assert expired[1]["error"]["code"] == "REMOTE_UNAUTHORIZED"
        replacement = await remote.create_remote_session(
            claimed["device_credential"], device_id=device_id
        )
        paired.auth_token = replacement["session_token"]
        assert await paired.list_messages()

        control_invitation = await local.create_pairing_invitation(
            "Control phone",
            scopes=["tasks:read", "tasks:control"],
        )
        control_device_id = "phone-control-0001"
        control_remote = SoraApiClient(
            base_url=remote_origin,
            origin=remote_origin,
            device_id=control_device_id,
            ssl_context=unverified_test_context(),
        )
        control_claim = await control_remote.claim_pairing(
            control_invitation["pairing_code"],
            device_id=control_device_id,
            label="Control phone",
        )
        control_session = await control_remote.create_remote_session(
            control_claim["device_credential"], device_id=control_device_id
        )
        controller = SoraApiClient(
            base_url=remote_origin,
            auth_token=control_session["session_token"],
            authorization_scheme="SoraSession",
            origin=remote_origin,
            device_id=control_device_id,
            ssl_context=unverified_test_context(),
        )
        remote_task = await controller.submit_task("scoped remote task")
        assert remote_task["task_id"].startswith("task-")
        control_dialogue = await controller.dialogue("this scope must not allow dialogue")
        assert control_dialogue["error"]["code"] == "REMOTE_SCOPE_DENIED"

        devices = await local.list_paired_devices()
        devices_by_id = {item["device_id"]: item for item in devices["devices"]}
        assert device_id in devices_by_id
        assert control_device_id in devices_by_id
        assert "credential_hash" not in devices_by_id[device_id]
        revoked = await local.revoke_paired_device(device_id)
        assert revoked["revoked"] is True
        after_revoke = await paired._request_dict("GET", "/api/v1/messages")
        assert after_revoke[1]["error"]["code"] == "REMOTE_UNAUTHORIZED"

        audit = await local.list_remote_audit(100)
        audit_text = json.dumps(audit)
        assert invitation["pairing_code"] not in audit_text
        assert control_invitation["pairing_code"] not in audit_text
        assert claimed["device_credential"] not in audit_text
        assert session["session_token"] not in audit_text
        assert replacement["session_token"] not in audit_text
        assert control_session["session_token"] not in audit_text
        actions = {entry["action"] for entry in audit["audit"]}
        assert {"pairing.claim", "session.create", "request.route", "device.revoke"} <= actions
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_pairing_attempts_are_rate_limited(tmp_path: Path, unused_tcp_port: int) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = "remote-rate-token-abcdef-123456"
    server = SoraApiServer(runtime, remote_config(token, unused_tcp_port, pairing_limit=2))
    await server.start()
    origin = f"https://127.0.0.1:{unused_tcp_port}"
    remote = SoraApiClient(
        base_url=origin,
        origin=origin,
        device_id="phone-rate-0001",
        ssl_context=unverified_test_context(),
    )
    try:
        first = await remote.claim_pairing(
            "wrong-code", device_id="phone-rate-0001", label="Rate phone"
        )
        second = await remote.claim_pairing(
            "wrong-code", device_id="phone-rate-0001", label="Rate phone"
        )
        limited = await remote.claim_pairing(
            "wrong-code", device_id="phone-rate-0001", label="Rate phone"
        )
        assert first["error"]["code"] == "PAIRING_REJECTED"
        assert second["error"]["code"] == "PAIRING_REJECTED"
        assert limited["error"]["code"] == "RATE_LIMITED"
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_device_session_and_revocation_survive_core_restart(tmp_path: Path) -> None:
    root = tmp_path / "runtime"
    runtime = SoraRuntime(
        RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    manager = RemoteAccessManager(runtime.repository.database, runtime.config.owner_id)
    invitation = await manager.create_invitation(label="Restart phone")
    claimed = await manager.claim_invitation(
        code=invitation["pairing_code"],
        device_id="phone-restart-0001",
        label="Restart phone",
        source_ip="127.0.0.1",
    )
    session = await manager.create_session(
        authorization=f"SoraDevice {claimed['device_credential']}",
        device_id="phone-restart-0001",
        requested_scopes=None,
        source_ip="127.0.0.1",
    )
    await runtime.close()

    reopened = SoraRuntime(
        RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await reopened.start()
    reopened_manager = RemoteAccessManager(
        reopened.repository.database, reopened.config.owner_id
    )
    principal = await reopened_manager.authenticate_session(
        authorization=f"SoraSession {session['session_token']}",
        device_id="phone-restart-0001",
    )
    assert principal.session_id == session["session_id"]
    await reopened_manager.revoke_device("phone-restart-0001", source_ip="127.0.0.1")
    await reopened.close()

    revoked_restart = SoraRuntime(
        RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await revoked_restart.start()
    revoked_manager = RemoteAccessManager(
        revoked_restart.repository.database, revoked_restart.config.owner_id
    )
    with pytest.raises(RemoteAccessError, match="invalid"):
        await revoked_manager.authenticate_session(
            authorization=f"SoraSession {session['session_token']}",
            device_id="phone-restart-0001",
        )
    await revoked_restart.close()


@pytest.mark.asyncio
async def test_concurrent_pairing_claim_consumes_invitation_once(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    manager = RemoteAccessManager(runtime.repository.database, runtime.config.owner_id)
    invitation = await manager.create_invitation(label="One claimant")
    results = await asyncio.gather(
        manager.claim_invitation(
            code=invitation["pairing_code"],
            device_id="phone-race-0001",
            label="Race one",
            source_ip="127.0.0.1",
        ),
        manager.claim_invitation(
            code=invitation["pairing_code"],
            device_id="phone-race-0002",
            label="Race two",
            source_ip="127.0.0.1",
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, dict) for result in results) == 1
    denied = [result for result in results if isinstance(result, RemoteAccessError)]
    assert len(denied) == 1
    assert denied[0].code == "PAIRING_USED"
    devices = await manager.list_devices()
    assert len(devices) == 1
    await runtime.close()
