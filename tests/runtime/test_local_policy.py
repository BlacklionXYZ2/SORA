"""Static owner policy is not a disguised grant; remote authority stays separate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.models import CapabilityOperation
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import (
    LocalCompanionPolicy,
    LocalPolicyContext,
    is_owner_local,
    operation_effects,
    owner_local_scope,
)
from sora.security.operations import OperationAuthorizationError

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def test_v2_migration_preserves_original_and_explicit_disables(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    payload = AppSettings(revision=7).model_dump(mode="json")
    payload.update(version=2, local_companion={"file_read": False})
    original = json.dumps(payload)
    path.write_text(original, encoding="utf-8")
    controller = AppSettingsController(tmp_path, AppSettings(), path=path)
    assert controller.saved.version == 9 and controller.saved.revision == 7
    assert not controller.active.local_companion.file_read
    assert not controller.active.local_companion.direct_file_write
    assert controller.active.local_companion.desktop_observe
    assert next(tmp_path.glob("settings.v2-*.json")).read_text() == original
    assert json.loads(path.read_text())["version"] == 9


def test_corrupt_startup_recovers_disables_or_fails_closed(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    controller.save(SettingsEdit(version=3, expected_revision=0, changes={
        "local_companion.file_read": False, "local_companion.desktop_capture": False,
    }))
    controller.store.path.write_text("not json", encoding="utf-8")
    recovered = AppSettingsController(tmp_path, AppSettings())
    assert not recovered.active.local_companion.file_read
    assert not recovered.active.local_companion.desktop_capture
    assert "restored" in recovered.disk_error
    assert controller.store.path.read_text() == "not json"
    (controller.store.path.parent / "sora-settings.recovery.json").unlink()
    stopped = AppSettingsController(tmp_path, AppSettings())
    assert stopped.active.local_companion == LocalCompanionPolicy.disabled()


def test_missing_v3_fields_do_not_silently_restore_defaults(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    payload = controller.saved.model_dump(mode="json")
    del payload["local_companion"]["file_read"]
    controller.store.path.write_text(json.dumps(payload), encoding="utf-8")
    controller.refresh()
    assert controller.disk_error
    with pytest.raises(ValueError):
        LocalCompanionPolicy(file_read="false")  # type: ignore[arg-type]


def test_explicit_effects_and_context_scope() -> None:
    assert not is_owner_local()
    with owner_local_scope():
        assert is_owner_local()
    assert not is_owner_local()
    assert operation_effects(CapabilityOperation.DESKTOP_OBSERVE, "desktop.capture:region:x") == (
        "desktop_capture",
    )
    with pytest.raises(OperationAuthorizationError, match="registered"):
        operation_effects(CapabilityOperation.TOOL_INVOKE, "arbitrary.write_file")
    with pytest.raises(OperationAuthorizationError, match="disabled"):
        LocalCompanionPolicy().require(("direct_file_write",))


@pytest.mark.asyncio
async def test_local_http_needs_no_grants_and_disabled_policy_cannot_be_bypassed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="local-policy-test-token"))
    await server.start()
    forbidden = AsyncMock(side_effect=AssertionError("Local policy must not use grant storage"))
    for name in ("save_grant", "save_approval", "consume_grant"):
        monkeypatch.setattr(runtime.repository, name, forbidden)
    try:
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{server.actual_port}") as client:
            headers = {"Authorization": "Bearer local-policy-test-token",
                       "X-SORA-Device-ID": "device-local"}
            denied = await client.post("/api/v1/desktop/observe", json={
                "operation": "windows", "process_id": 123,
            })
            assert denied.status_code == 401
            observed = await client.post("/api/v1/desktop/observe", headers=headers,
                                         json={"operation": "windows", "process_id": 123})
            assert observed.status_code == 200, observed.text
            assert observed.json()["status"] == "not_configured"
            saved = await client.post("/api/v1/settings", headers=headers, json={
                "version": 3, "expected_revision": 0,
                "changes": {"local_companion.desktop_observe": False},
            })
            assert saved.status_code == 200, saved.text
            disabled = await client.post("/api/v1/desktop/observe", headers={
                **headers, "X-SORA-Grant-ID": "forged-grant",
            }, json={"operation": "windows", "process_id": 123})
            assert disabled.status_code == 403
        # A forged device name alone never enters local policy (remote/internal caller).
        with pytest.raises(OperationAuthorizationError, match="grant_id"):
            await runtime.authorize_operation(grant_id="", device_id="device-local",
                resource="desktop.observe:123", operation=CapabilityOperation.DESKTOP_OBSERVE)
        forbidden.assert_not_awaited()
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_policy_epoch_rejects_pending_work_after_off_then_on(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    try:
        with owner_local_scope():
            authority = await runtime.authorize_operation(grant_id="", device_id="device-local",
                resource="desktop.observe:123", operation=CapabilityOperation.DESKTOP_OBSERVE)
        assert isinstance(authority, LocalPolicyContext)
        assert "grant" not in authority.model_dump() and "approval" not in authority.model_dump()
        for enabled in (False, True):
            settings.save(SettingsEdit(version=3, expected_revision=settings.saved.revision,
                changes={"local_companion.desktop_observe": enabled}))
        with pytest.raises(OperationAuthorizationError, match="changed"):
            await runtime.consume_operation(authority)
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(("setting", "operation", "resource"), [
    ("desktop_observe", CapabilityOperation.DESKTOP_OBSERVE, "desktop.observe:123"),
    ("desktop_capture", CapabilityOperation.DESKTOP_OBSERVE, "desktop.capture:region:test"),
    ("file_read", CapabilityOperation.PATH_READ, "C:/fixture/example.txt"),
    ("desktop_interact", CapabilityOperation.DESKTOP_INTERACT, "desktop.interact:test"),
    ("avatar_control", CapabilityOperation.TOOL_INVOKE, "embodiment.command"),
    ("voice", CapabilityOperation.VOICE_SESSION, "voice.session:test"),
    ("direct_file_write", CapabilityOperation.PATH_WRITE, "C:/fixture/example.txt"),
])
async def test_each_registered_effect_obeys_its_static_switch(
    tmp_path: Path, setting: str, operation: CapabilityOperation, resource: str,
) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    try:
        settings.save(SettingsEdit(version=3, expected_revision=0,
            changes={f"local_companion.{setting}": False}))
        with owner_local_scope(), pytest.raises(OperationAuthorizationError, match="disabled"):
            await runtime.authorize_operation(grant_id="not-a-bypass", device_id="device-local",
                resource=resource, operation=operation)
    finally:
        await runtime.close()
