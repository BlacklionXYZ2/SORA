"""Managed shutdown needs owner auth, launch authority, epoch and delivered ACK."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.lifecycle import CONTROL_ENV, SESSION_ENV, ManagedLifecycle
from sora.api.protocol import HttpRequest, HttpResponse
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings
from sora.runtime.service import RuntimeConfig, SoraRuntime

SECRET = "test-only-managed-launch-credential-123456789"
IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.parametrize("environment", [
    {SESSION_ENV: str(uuid4())}, {CONTROL_ENV: SECRET},
    {SESSION_ENV: "invalid-session-private-value", CONTROL_ENV: SECRET},
    {SESSION_ENV: str(uuid4()), CONTROL_ENV: "invalid-private-credential"},
])
def test_bad_launch_environment_is_consumed_without_echoing_values(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str],
) -> None:
    for key in (SESSION_ENV, CONTROL_ENV):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError) as error:
        ManagedLifecycle.from_environment()
    assert not any(value in str(error.value) for value in environment.values())
    assert ManagedLifecycle.from_environment() is None


def test_valid_launch_environment_is_not_inherited(monkeypatch: pytest.MonkeyPatch) -> None:
    session = uuid4()
    monkeypatch.setenv(SESSION_ENV, str(session))
    monkeypatch.setenv(CONTROL_ENV, SECRET)
    lifecycle = ManagedLifecycle.from_environment()
    assert lifecycle is not None and lifecycle.session_id == session
    assert ManagedLifecycle.from_environment() is None
    assert SECRET not in repr(lifecycle)
    assert SECRET not in repr(lifecycle._credential)


def command(lifecycle: ManagedLifecycle, epoch: str, **overrides: object) -> HttpRequest:
    body = {"version": 1, "managed_session_id": str(lifecycle.session_id),
            "request_id": str(uuid4())} | overrides
    return HttpRequest("POST", "/api/v1/runtime/shutdown", {
        "X-SORA-Core-Instance": epoch, "X-SORA-Host-Control": SECRET,
    }, json.dumps(body).encode())


@pytest.mark.asyncio
async def test_managed_route_rejects_remote_external_wrong_session_and_stale_epoch(
    tmp_path: Path,
) -> None:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider())
    await runtime.start()
    lifecycle = ManagedLifecycle(uuid4(), SECRET)
    server = SoraApiServer(runtime, lifecycle=lifecycle)
    external = SoraApiServer(runtime)
    try:
        epoch = server.routes.instance_id
        request = command(lifecycle, epoch)
        assert (await server.routes.handle_request(
            request, remote_scopes=frozenset({"runtime.shutdown"}),
        )).status_code == 403
        assert (await external.routes.handle_request(
            command(lifecycle, external.routes.instance_id),
        )).status_code == 403
        request.headers.pop("x-sora-host-control")
        assert (await server.routes.handle_request(request)).status_code == 403
        request.headers["x-sora-host-control"] = "wrong-private-credential-123456789012"
        assert (await server.routes.handle_request(request)).status_code == 403
        request.headers["x-sora-host-control"] = "non-ascii-\u00e9"
        assert (await server.routes.handle_request(request)).status_code == 403
        request = command(lifecycle, epoch)
        request.headers.pop("x-sora-core-instance")
        assert (await server.routes.handle_request(request)).status_code == 409
        stale = await server.routes.handle_request(command(lifecycle, str(uuid4())))
        assert stale.status_code == 409
        assert (await server.routes.handle_request(
            command(lifecycle, epoch, managed_session_id=str(uuid4())),
        )).status_code == 409
        assert not lifecycle.shutdown.is_set()
        projection = await external.routes.handle_request(
            HttpRequest("GET", "/api/v1/runtime/lifecycle", {}, b""),
        )
        assert projection.parse_json()["state"] == "external"
        assert projection.parse_json()["managed_session_id"] is None
    finally:
        await runtime.close()


@pytest.mark.parametrize("body", [
    b"{}", b"null", b"[]", b"invalid", b'{"version":2}', b"x" * 1025,
])
def test_invalid_commands_do_not_signal_or_expose_request(body: bytes) -> None:
    lifecycle = ManagedLifecycle(uuid4(), SECRET)
    request = command(lifecycle, str(uuid4()))
    request.body = body
    response = lifecycle.request_shutdown(request, request.headers["x-sora-core-instance"])
    assert response.status_code in {400, 413}
    assert not lifecycle.shutdown.is_set() and response.after_send is None
    assert SECRET.encode() not in response.body


def test_acceptance_is_not_shutdown_and_only_exact_nonce_can_retry() -> None:
    lifecycle = ManagedLifecycle(uuid4(), SECRET)
    epoch = str(uuid4())
    request = command(lifecycle, epoch)
    first = lifecycle.request_shutdown(request, epoch)
    assert first.status_code == 202 and not lifecycle.shutdown.is_set()
    retry = lifecycle.request_shutdown(request, epoch)
    assert retry.body == first.body and not lifecycle.shutdown.is_set()
    conflict = lifecycle.request_shutdown(command(lifecycle, epoch), epoch)
    assert conflict.status_code == 409 and conflict.after_send is None
    assert first.after_send is not None
    first.after_send()
    assert lifecycle.shutdown.is_set()
    assert SECRET.encode() not in first.serialize()
    UUID(first.parse_json()["shutdown_request_id"])


@pytest.mark.asyncio
async def test_owner_http_auth_and_transport_acknowledgement(tmp_path: Path) -> None:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider())
    await runtime.start()
    lifecycle = ManagedLifecycle(uuid4(), SECRET)
    server = SoraApiServer(runtime, ApiServerConfig(port=0), lifecycle=lifecycle)
    await server.start()
    client = SoraApiClient(f"http://127.0.0.1:{server.actual_port}", server.config.auth_token)
    try:
        status, projection = await client._request_dict("GET", "/api/v1/runtime/lifecycle")
        assert status == 200 and projection["state"] == "managed"
        assert SECRET not in json.dumps(projection)
        request = command(lifecycle, server.routes.instance_id)
        headers = request.headers
        unauth = SoraApiClient(client.base_url)
        assert (await unauth._request_dict("POST", request.path,
                                           body=request.json(), headers=headers))[0] == 401
        assert not lifecycle.shutdown.is_set()
        status, acknowledgement = await client._request_dict(
            "POST", request.path, body=request.json(), headers=headers,
        )
        assert status == 202 and acknowledgement["state"] == "shutdown_requested"
        await asyncio.wait_for(lifecycle.shutdown.wait(), timeout=1)
        # Accepted shutdown quiesces admission, even while normal cleanup drains
        # previously admitted work. A lost ACK cannot create an effect replay gap.
        denied, error = await client._request_dict(
            "POST", "/api/v1/messages", body={"content": "must not be admitted"},
        )
        assert denied == 503 and error["error"]["code"] == "RUNTIME_SHUTTING_DOWN"
        assert await client.list_messages(limit=10) == []
    finally:
        await server.close()
        await runtime.close()


class FixtureWriter:
    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.drained = False
        self.closed = False

    def write(self, data: bytes) -> None:
        assert b"HTTP/1.1 202" in data

    async def drain(self) -> None:
        if self.fail:
            raise ConnectionError("fixture failed delivery")
        self.drained = True

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [False, True])
async def test_completion_hook_runs_only_after_successful_drain(fail: bool) -> None:
    writer = FixtureWriter(fail=fail)
    response = HttpResponse(202)
    completed: list[bool] = []
    response.after_send = lambda: completed.append(writer.drained)
    # No runtime or listener is needed to test the actual transport method.
    await SoraApiServer._send_http_response(None, writer, response)  # type: ignore[arg-type]
    assert completed == ([] if fail else [True])
    assert writer.closed


@pytest.mark.asyncio
async def test_real_cli_owned_core_exits_gracefully_after_acknowledgement(tmp_path: Path) -> None:
    root = tmp_path / "managed-cli"
    root.mkdir()
    settings = AppSettings().model_dump(mode="json")
    settings["local_companion"] = {key: False for key in settings["local_companion"]}
    settings_file = root / "settings.json"
    settings_file.write_text(json.dumps(settings), encoding="utf-8")
    token_file = root / "private" / "api-token"
    session = uuid4()
    environment = dict(os.environ) | {SESSION_ENV: str(session), CONTROL_ENV: SECRET}
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-u", "-m", "sora", "--root", str(root),
        "--identity-root", str(IDENTITY_ROOT), "--settings", str(settings_file),
        "--provider", "deterministic", "--serve", "--api-port", "0",
        "--api-token-file", str(token_file),
        env=environment, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    output: list[str] = []
    try:
        async with asyncio.timeout(30):
            while True:
                line = (await process.stdout.readline()).decode("utf-8").strip()
                output.append(line)
                if line.startswith("SORA API Server running on "):
                    endpoint = line.removeprefix("SORA API Server running on ")
                    break
                if not line:
                    raise AssertionError("CLI exited before becoming ready: " + "\n".join(output))
        client = SoraApiClient(endpoint, token_file.read_text(encoding="utf-8"))
        status, identity = await client._request_dict("GET", "/api/v1/runtime/identity")
        assert status == 200 and identity["state_root"] == str(root.resolve())
        status, owned = await client._request_dict("GET", "/api/v1/runtime/lifecycle")
        assert status == 200 and owned["managed_session_id"] == str(session)
        epoch = identity["instance_id"]
        body = {"version": 1, "managed_session_id": str(session), "request_id": str(uuid4())}
        denied, _ = await client._request_dict(
            "POST", "/api/v1/runtime/shutdown", body=body,
            headers={"X-SORA-Core-Instance": epoch},
        )
        assert denied == 403 and process.returncode is None
        status, acknowledged = await client._request_dict(
            "POST", "/api/v1/runtime/shutdown", body=body,
            headers={"X-SORA-Core-Instance": epoch, "X-SORA-Host-Control": SECRET},
        )
        assert status == 202 and acknowledged["shutdown_request_id"] == body["request_id"]
        assert await asyncio.wait_for(process.wait(), timeout=10) == 0
        output.append((await process.stdout.read()).decode("utf-8"))
        assert SECRET not in "\n".join(output)
        assert SECRET not in settings_file.read_text(encoding="utf-8")
        with pytest.raises((ConnectionRefusedError, OSError)):
            await asyncio.wait_for(client._request_dict("GET", "/healthz"), timeout=2)
    finally:
        if process.returncode is None:
            # Failure-only cleanup targets this exact synthetic child, never a
            # process name/profile. Reaching it cannot count as graceful evidence.
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
