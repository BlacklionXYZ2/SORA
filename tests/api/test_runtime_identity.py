"""Profile identity is authenticated/owner-local; instance binding rejects old effects."""

from pathlib import Path
from uuid import UUID

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_runtime_identity_and_epoch_binding(tmp_path: Path) -> None:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider())
    await runtime.start()
    server = SoraApiServer(
        runtime, ApiServerConfig(port=0, auth_token="identity-fixture-token-12345"),
    )
    await server.start()
    client = SoraApiClient(base_url=f"http://127.0.0.1:{server.actual_port}",
                          auth_token="identity-fixture-token-12345")
    try:
        status, identity = await client._request_dict("GET", "/api/v1/runtime/identity")
        assert status == 200 and identity["version"] == 1
        UUID(identity["instance_id"])
        assert identity["state_root"] == str(tmp_path.resolve())
        assert identity["owner_id"] == runtime.config.owner_id
        assert "token" not in str(identity)
        request = HttpRequest(method="GET", path="/api/v1/runtime/identity", headers={}, body=b"")
        forbidden = await server.routes.handle_request(request, remote_scopes=frozenset())
        assert forbidden.status_code == 403
        stale = HttpRequest(method="POST", path="/api/v1/messages",
                            headers={"x-sora-core-instance": "stale"},
                            body=b'{"content":"must not write"}')
        rejected = await server.routes.handle_request(stale)
        assert rejected.status_code == 409 and b"RUNTIME_CHANGED" in rejected.body
        assert await client.list_messages(limit=10) == []
        matching = HttpRequest(method="GET", path="/api/v1/status",
                              headers={"x-sora-core-instance": identity["instance_id"]}, body=b"")
        assert (await server.routes.handle_request(matching)).status_code == 200
        assert SoraApiServer(runtime).routes.instance_id != identity["instance_id"]
        unauth = SoraApiClient(base_url=f"http://127.0.0.1:{server.actual_port}",
                              auth_token="wrong-token-123456789")
        assert (await unauth._request_dict("GET", "/api/v1/runtime/identity"))[0] == 401
    finally:
        await server.close()
        await runtime.close()
