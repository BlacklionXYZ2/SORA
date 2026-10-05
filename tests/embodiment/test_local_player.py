from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.models import GrantStatus
from sora.embodiment.local_player import LocalAvatarSession
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError


class FakePlayer:
    returncode: int | None = None

    def terminate(self) -> None:
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode or 0


@pytest.mark.asyncio
async def test_local_avatar_scopes_credentials_and_revokes_on_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = SoraRuntime(RuntimeConfig(
        root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity",
    ), provider=DeterministicProvider())
    await runtime.start()
    calls: list[dict[str, Any]] = []
    player = FakePlayer()

    async def spawn(*args: str, **kwargs: Any) -> FakePlayer:
        calls.append({"args": args, **kwargs})
        return player

    monkeypatch.setattr("sora.embodiment.local_player.asyncio.create_subprocess_exec", spawn)
    monkeypatch.setenv("SORA_INTERACTION_EVIDENCE_PATH", "unwanted-fixture")
    session = LocalAvatarSession(runtime, Path(sys.executable))
    try:
        await session.start(token="private-avatar-token", port=12345)
        assert "private-avatar-token" not in str(calls[0]["args"])
        env = calls[0]["env"]
        assert env["SORA_API_TOKEN"] == "private-avatar-token"
        assert env["SORA_CORE_PORT"] == "12345"
        assert "SORA_INTERACTION_EVIDENCE_PATH" not in env
        assert "SORA_EMBODIMENT_COMMAND_GRANT" not in env
        for operation in ("connect", "topology", "command"):
            grant = session._grants[operation]
            auth = await runtime.authorize_operation(
                grant_id=grant.grant_id, device_id="device-local",
                resource=f"embodiment.{operation}",
            )
            assert auth.authorized_by == "owner-local"
        with pytest.raises(ValueError, match="Unknown companion pose"):
            await session.present("press")
        await session.close()
        assert player.returncode == 0
        for grant in session._grants.values():
            stored = await runtime.repository.get_grant(grant.grant_id)
            assert stored is not None and stored.status is GrantStatus.REVOKED
    finally:
        await session.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_companion_control_is_local_and_requires_managed_session(tmp_path: Path) -> None:
    runtime = SoraRuntime(RuntimeConfig(
        root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity",
    ), provider=DeterministicProvider())
    await runtime.start()
    try:
        routes = RouteHandler(runtime)
        for method in ("GET", "POST"):
            request = HttpRequest(method=method, path="/api/v1/companion", headers={}, body=b"")
            denied = await routes.handle_request(request, remote_scopes=frozenset({"tasks:read"}))
            assert denied.status_code == 403
        response = await routes.handle_request(HttpRequest(
            method="POST", path="/api/v1/companion", headers={}, body=b'{"state":"waving"}',
        ))
        assert response.status_code == 409
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_settings_backed_avatar_dispatch_and_revocation_without_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(RuntimeConfig(
        root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity",
    ), provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    player = FakePlayer()
    calls: list[dict[str, Any]] = []

    async def spawn(*args: str, **kwargs: Any) -> FakePlayer:
        calls.append(kwargs)
        return player

    monkeypatch.setattr("sora.embodiment.local_player.asyncio.create_subprocess_exec", spawn)
    forbidden = AsyncMock(side_effect=AssertionError("No local grant records"))
    for name in ("save_grant", "save_approval", "consume_grant"):
        monkeypatch.setattr(runtime.repository, name, forbidden)
    session = LocalAvatarSession(runtime, Path(sys.executable))
    queue = runtime.register_embodiment_queue()
    try:
        await session.start(token="fixture-only-avatar-token", port=12345)
        assert calls[0]["env"]["SORA_EMBODIMENT_CONNECT_GRANT"] == ""
        assert not session._grants
        await session.present("waving")
        command = queue.get_nowait()
        assert await runtime.validate_embodiment_delivery(command)
        settings.save(SettingsEdit(version=3, expected_revision=0,
            changes={"local_companion.avatar_control": False}))
        assert not await runtime.validate_embodiment_delivery(command)
        with pytest.raises(OperationAuthorizationError, match="disabled"):
            await session.present("sitting")
        forbidden.assert_not_awaited()
    finally:
        await session.close()
        runtime.unregister_embodiment_queue(queue)
        await runtime.close()
