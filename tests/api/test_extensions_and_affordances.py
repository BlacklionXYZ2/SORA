"""Tests for extension registration, enable/disable lifecycle,
and capability invalidation (P08.6).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.models import GrantStatus
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_extensions_enable_disable_lifecycle(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
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
        # List registered extensions (built-in fake Integration and Desktop Component)
        extensions = await client.list_extensions()
        assert len(extensions) >= 2
        ext_ids = [e["extension_id"] for e in extensions]
        assert "integration-media-player" in ext_ids
        assert "component-kanban-board" in ext_ids

        # Disabled by default until an exact persisted grant enables it.
        caps = await client.get_capabilities_projection()
        assert "integration-media-player" not in caps["active_extensions"]

        schema = await client.get_extension_schema("integration-media-player")
        assert schema["version"] == "1.0.0"
        assert schema["schema"]["$id"] == "sora://extensions/media-player/1.0.0"

        _, missing_grant = await client._request_dict(
            "POST", "/api/v1/extensions/integration-media-player/enable", body={}
        )
        assert missing_grant["error"]["code"] == "AUTHORIZATION_REQUIRED"

        authorization = await persist_operation_grant(
            runtime,
            "extension.control:integration-media-player",
            grant_id="grant-media-control",
        )

        enabled = await client.enable_extension(
            "integration-media-player", grant_id="grant-media-control"
        )
        assert enabled["enabled"] is True
        caps_enabled = await client.get_capabilities_projection()
        assert "integration-media-player" in caps_enabled["active_extensions"]

        other_device = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token=token,
            device_id="device-other",
        )
        other_caps = await other_device.get_capabilities_projection()
        assert "integration-media-player" not in other_caps["active_extensions"]

        # Disable extension: should immediately invalidate from active extensions
        disabled = await client.disable_extension("integration-media-player")
        assert disabled["enabled"] is False

        caps_after = await client.get_capabilities_projection()
        assert "integration-media-player" not in caps_after["active_extensions"]

        # Re-enable extension and prove the configured state survives server restart.
        enabled = await client.enable_extension(
            "integration-media-player", grant_id="grant-media-control"
        )
        assert enabled["enabled"] is True

        caps_restored = await client.get_capabilities_projection()
        assert "integration-media-player" in caps_restored["active_extensions"]

        await server.close()
        server = SoraApiServer(runtime, api_cfg)
        await server.start()
        client = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token=token,
        )
        extensions_after_restart = await client.list_extensions()
        media = next(
            ext
            for ext in extensions_after_restart
            if ext["extension_id"] == "integration-media-player"
        )
        assert media["enabled"] is True

        # Grant revocation removes the extension from the active set immediately.
        await runtime.repository.save_grant(
            authorization.grant.model_copy(update={"status": GrantStatus.REVOKED})
        )
        caps_revoked = await client.get_capabilities_projection()
        assert "integration-media-player" not in caps_revoked["active_extensions"]

    finally:
        await server.close()
        await runtime.close()
