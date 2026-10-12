"""Unified settings persistence, effect boundaries and model reload fault injection."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import httpx
import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.providers.dialogue import DialogueProviderError
from sora.providers.llama_server import LlamaServerConfig, ManagedLlamaServer
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import (
    FIELDS,
    SETTINGS_ADVANCED_KEYS,
    SETTINGS_CATEGORIES,
    SETTINGS_CATEGORY_KEYS,
    TIERS,
    AppSettings,
    AppSettingsController,
    ReloadRequest,
    SettingsConflict,
    SettingsEdit,
    discover_projectors,
    flatten,
)
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.runtime.settings import RuntimeSettingsStore, SavedRuntimeSettings

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.fixture
def configured(tmp_path: Path) -> AppSettings:
    for name in ("model.gguf", "mmproj.gguf", "draft.gguf"):
        (tmp_path / name).write_bytes(b"GGUFfixture")
    return AppSettings.model_validate(
        {
            "dialogue": {"backend": "managed-llama"},
            "llama": {
                "executable": __file__,
                "model_path": tmp_path / "model.gguf",
                "mmproj_path": tmp_path / "mmproj.gguf",
            },
        }
    )


class FakeServer(ManagedLlamaServer):
    closed = False
    fail_context = -1

    async def inspect_runtime(self) -> str:
        return "Fake runtime supports fixture flags"

    async def start(self) -> None:
        if self.config.context_size == type(self).fail_context:
            raise RuntimeError("simulated model failure")

    async def close(self) -> None:
        self.closed = True


def edit(controller: AppSettingsController, **changes: object) -> SettingsEdit:
    return SettingsEdit(version=2, expected_revision=controller.saved.revision, changes=changes)


def test_all_preferences_have_controls_and_tiers() -> None:
    defaults = flatten(AppSettings().model_dump(mode="json"))
    assert set(TIERS) == set(defaults) - {"revision", "version", "delegation_epoch"}
    assert len(FIELDS) == len(TIERS)
    assert FIELDS[0]["group"] == "Companion access"
    assert {field["type"] for field in FIELDS} >= {"gpu", "enum", "int", "bool", "path-gguf"}


def test_gui_categories_cover_every_v10_preference_once_without_new_authority() -> None:
    keys = [key for group in SETTINGS_CATEGORY_KEYS.values() for key in group]
    assert len(keys) == len(set(keys)) == len(FIELDS) == 145
    assert set(keys) == set(TIERS)
    assert SETTINGS_ADVANCED_KEYS <= set(keys)
    assert len(SETTINGS_CATEGORIES) == 10
    for field in FIELDS:
        assert field["category"] in SETTINGS_CATEGORIES
        assert field["key"] in SETTINGS_CATEGORY_KEYS[field["category"]]
        assert field["advanced"] == (field["key"] in SETTINGS_ADVANCED_KEYS)
        assert field["tier"] == TIERS[field["key"]]
        assert field["editable"] is True
    # These need real services/UI-only preferences, not invented canonical knobs. Memory has
    # one since 2026-10-09 (the memory manager), Appearance since 2026-10-11 (the avatar).
    assert not {f["category"] for f in FIELDS} & {"Automation"}
    assert [f["key"] for f in FIELDS if f["category"] == "Appearance"] == ["avatar.vrm_path"]
    assert {f["key"] for f in FIELDS if f["category"] == "Memory"} == {
        "memory.mode", "memory.device", "memory.server", "memory.model_path"}
    assert next(f for f in FIELDS if f["key"] == "local_companion.file_read")["category"] == "Tools"
    capture = next(f for f in FIELDS if f["key"] == "local_companion.desktop_capture")
    assert capture["category"] == "Vision"


@pytest.mark.asyncio
async def test_live_and_boot_edits_do_not_create_false_model_pending(
    tmp_path: Path,
    configured: AppSettings,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    try:
        assert getattr(controller.provider, "display_name", None) == "model.gguf"
        view = controller.save(edit(controller, **{"dialogue.timeout_seconds": 60}))
        assert not view["model_reload_required"] and not view["restart_required"]
        assert controller.provider.timeout_seconds == 60  # type: ignore[attr-defined]
        view = controller.save(edit(controller, **{"llama.port": 18779}))
        assert view["restart_required"] and not view["model_reload_required"]
        controller.save(edit(controller, **{"llama.context_size": 4096}))
        controller.request_reload(ReloadRequest(expected_revision=controller.saved.revision))
        assert controller.task is not None
        await controller.task
        assert controller.active.llama.port == 18771  # next-boot boundary
        assert controller.active.llama.context_size == 4096
        assert controller.projection()["restart_required"]
        assert not controller.projection()["model_reload_required"]
        view = controller.save(edit(controller, **{"llama.port": 18771}))
        assert not view["restart_required"]
        assert controller.server is not None
        assert controller.server.api_key not in controller.store.path.read_text()
    finally:
        await controller.close()


@pytest.mark.asyncio
async def test_launch_details_distinguish_capture_reload_and_next_start(
    tmp_path: Path, configured: AppSettings,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    try:
        assert controller.server is not None
        # Explicit process/capture fixture. FakeServer alone is not launch evidence.
        controller.server.process = cast(asyncio.subprocess.Process, Mock(returncode=None))
        captured = tuple(controller.server.config.command())
        controller.server.launch_arguments = captured
        controller.save(edit(controller, **{"llama.port": 18779, "llama.context_size": 4096}))
        details = controller.projection()["launch_details"]
        assert details["version"] == 1
        assert details["active"]["argv"] == list(captured)
        reload_args, start_args = details["next_reload"]["argv"], details["next_start"]["argv"]
        assert reload_args[reload_args.index("--port") + 1] == "18771"
        assert start_args[start_args.index("--port") + 1] == "18779"
        assert reload_args[reload_args.index("--ctx-size") + 1] == "4096"
        assert captured[captured.index("--ctx-size") + 1] == "12288"  # medium vision detail
        assert controller.server.api_key not in json.dumps(details)
        controller.server.process = cast(asyncio.subprocess.Process, Mock(returncode=1))
        assert controller.launch_details()["active"]["argv"] is None
    finally:
        await controller.close()


def test_launch_previews_do_not_probe_files_runtime_or_invent_a_live_capture(
    tmp_path: Path, configured: AppSettings, monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    assert configured.llama.model_path is not None
    configured.llama.model_path.unlink()

    def no_validation(*args: object, **kwargs: object) -> None:
        raise AssertionError("Projection must not validate model files or launch a helper")

    monkeypatch.setattr(LlamaServerConfig, "model_validate", no_validation)
    details = controller.launch_details()
    assert details["active"]["argv"] is None
    assert details["next_reload"]["argv"] is not None
    assert "not file/runtime validated" in details["next_reload"]["note"]
    controller.saved = controller.saved.model_copy(update={
        "dialogue": controller.saved.dialogue.model_copy(update={"backend": "deterministic"}),
    })
    details = controller.launch_details()
    assert details["next_start"]["argv"] is None
    assert details["next_reload"]["argv"] is not None  # active boot backend stays managed


@pytest.mark.asyncio
async def test_reload_failure_restores_old_model_and_keeps_failed_edit_pending(
    tmp_path: Path,
    configured: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    monkeypatch.setattr(FakeServer, "fail_context", 4096)
    controller.save(edit(controller, **{"llama.context_size": 4096}))
    controller.request_reload(ReloadRequest(expected_revision=controller.saved.revision))
    assert controller.task is not None
    await controller.task
    assert controller.model_state == "ready" and controller.rollback_applied
    assert controller.active.llama.context_size == 12288  # medium vision detail
    assert controller.projection()["model_reload_required"]
    await controller.close()
    # Failed saved model at next boot still recovers, without replacing the requested settings.
    restarted = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await restarted.start()
    assert restarted.model_state == "ready" and restarted.rollback_applied
    assert restarted.saved.llama.context_size == 4096
    assert restarted.projection()["model_reload_required"]
    await restarted.close()


@pytest.mark.asyncio
async def test_busy_reload_quiesces_existing_turn_and_rejects_new_turns_and_edits(
    tmp_path: Path,
    configured: AppSettings,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    old = controller.server
    assert isinstance(old, FakeServer)
    async with controller.session():
        controller.request_reload(ReloadRequest(expected_revision=0))
        await asyncio.sleep(0)
        assert old is not None and not old.closed
        with pytest.raises(SettingsConflict):
            controller.request_reload(ReloadRequest(expected_revision=0))
        with pytest.raises(SettingsConflict):
            controller.save(edit(controller, **{"dialogue.timeout_seconds": 40}))
        with pytest.raises(DialogueProviderError):
            async with controller.session():
                pass
    assert controller.task is not None
    await controller.task
    assert old.closed and controller.model_state == "ready"
    await controller.close()


@pytest.mark.asyncio
async def test_bad_model_keeps_settings_repairable(tmp_path: Path, configured: AppSettings) -> None:
    configured.llama.model_path.unlink()  # type: ignore[union-attr]
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    assert controller.model_state == "down"
    assert controller.projection()["can_reload"]
    with pytest.raises(DialogueProviderError):
        async with controller.session():
            pass
    controller.save(edit(controller, **{"dialogue.timeout_seconds": 30}))
    await controller.close()


def test_disk_conflicts_invalid_backup_and_refresh(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    path = controller.store.path
    path.write_text("{")
    with pytest.raises(SettingsConflict):
        controller.save(edit(controller, **{"runtime.worker_count": 3}))
    assert path.read_text() == "{"
    repairing = AppSettingsController(tmp_path, AppSettings())
    assert repairing.disk_error
    repairing.save(edit(repairing, **{"runtime.worker_count": 3}))
    assert next(path.parent.glob("*.invalid-*.json")).read_text() == "{"
    assert json.loads(path.read_text())["runtime"]["worker_count"] == 3
    payload = json.loads(path.read_text())
    payload["runtime"]["worker_count"] = 4
    path.write_text(json.dumps(payload))
    repairing.refresh()
    assert repairing.saved.runtime.worker_count == 4
    path.write_text("not-json")
    repairing.refresh()
    assert repairing.disk_error
    repairing.save(edit(repairing))
    assert not repairing.disk_error
    assert any(p.read_text() == "not-json" for p in path.parent.glob("*.invalid-*.json"))


def test_model_options_flags_validation_and_projector_discovery(
    configured: AppSettings,
    tmp_path: Path,
) -> None:
    config = LlamaServerConfig.model_validate(
        {
            **configured.llama.model_dump(),
            "flash_attn": "on",
            "cache_type_k": "q8_0",
            "cache_type_v": "q8_0",
            "speculative": {"type": "draft-dflash", "draft_model_path": tmp_path / "draft.gguf"},
        }
    )
    command = config.command()
    for flag, value in (
        ("--flash-attn", "on"),
        ("--cache-type-v", "q8_0"),
        ("--spec-type", "draft-dflash"),
    ):
        assert command[command.index(flag) + 1] == value
    assert len(discover_projectors(str(config.model_path))) == 1
    (tmp_path / "mmproj-extra.gguf").write_bytes(b"GGUFfixture")
    assert len(discover_projectors(str(config.model_path))) == 2
    with pytest.raises(ValueError, match="Quantized V"):
        LlamaServerConfig.model_validate({**config.model_dump(), "flash_attn": "off"})
    with pytest.raises(ValueError, match="compatible draft"):
        LlamaServerConfig.model_validate(
            {**config.model_dump(), "speculative": {"type": "draft-mtp"}}
        )


@pytest.mark.asyncio
async def test_owner_settings_api_and_live_dialogue(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    await controller.start()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        app_settings=controller,
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="settings-test-token"))
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}", auth_token="settings-test-token"
    )
    try:
        status, settings = await client._request_dict("GET", "/api/v1/projections/settings")
        assert status == 200 and settings["settings_version"] == 10
        status, saved = await client._request_dict(
            "POST",
            "/api/v1/settings",
            {
                "version": 2,
                "expected_revision": 0,
                "changes": {"dialogue.timeout_seconds": 12, "runtime.worker_count": 3},
            },
        )
        assert status == 200 and saved["restart_required"]
        assert not saved["model_reload_required"]
        assert runtime.config.worker_count == 2
        assert "hello" in (await runtime.dialogue("hello")).lower()
        status, _ = await client._request_dict(
            "POST",
            "/api/v1/settings",
            {
                "version": 2,
                "expected_revision": 0,
                "changes": {},
            },
        )
        assert status == 409
        status, _ = await client._request_dict(
            "POST",
            "/api/v1/settings",
            {
                "version": 2,
                "expected_revision": 1,
                "changes": {"llama.api_key": "secret"},
            },
        )
        assert status == 422
        status, _ = await client._request_dict(
            "POST",
            "/api/v1/model/reload",
            {
                "expected_revision": 1,
            },
        )
        assert status == 422  # Not managed; source switch is next-boot only.
    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_cli_migrates_once_and_preserves_legacy_files(
    tmp_path: Path,
    configured: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sora.__main__ as cli

    store = RuntimeSettingsStore(tmp_path)
    store.save(
        SavedRuntimeSettings(
            version=1,
            revision=4,
            dialogue_backend="deterministic",
            dialogue_timeout_seconds=45,
            context_max_chars=9000,
            worker_count=3,
        )
    )
    legacy_llama = tmp_path / "llama-server.json"
    legacy_llama.write_text(configured.llama.model_dump_json())
    original_runtime = store.path.read_bytes()
    original_llama = legacy_llama.read_bytes()
    seen: list[AppSettings] = []

    async def no_load(self: AppSettingsController) -> None:
        pass

    async def capture(arguments: object, *, app_settings: AppSettingsController,
                      lifecycle: object = None) -> int:
        assert lifecycle is None  # Ordinary compatibility launch is never silently owned.
        seen.append(app_settings.saved)
        return 0

    monkeypatch.setattr(AppSettingsController, "start", no_load)
    monkeypatch.setattr(cli, "_run", capture)
    args = cli.parser().parse_args(["--root", str(tmp_path), "--llama-config", str(legacy_llama)])
    assert await cli.run(args) == 0
    assert seen[0].dialogue.backend == "managed-llama"
    assert seen[0].dialogue.timeout_seconds == 45 and seen[0].runtime.worker_count == 3
    assert (
        store.path.read_bytes() == original_runtime and legacy_llama.read_bytes() == original_llama
    )
    legacy_llama.write_text("invalid legacy JSON is no longer authoritative")
    assert await cli.run(args) == 0
    assert seen[0] == seen[1]


@pytest.mark.asyncio
async def test_rollback_failure_releases_child(
    tmp_path: Path,
    configured: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()

    async def fail(self: FakeServer) -> None:
        raise RuntimeError("backend failed")

    monkeypatch.setattr(FakeServer, "start", fail)
    controller.request_reload(ReloadRequest(expected_revision=0))
    assert controller.task is not None
    await controller.task
    assert controller.model_state == "down" and "Recovery also failed" in controller.last_error
    assert isinstance(controller.server, FakeServer) and controller.server.closed
    await controller.close()


@pytest.mark.asyncio
async def test_cancel_reload_releases_child(
    tmp_path: Path,
    configured: AppSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = AppSettingsController(tmp_path, configured, server_factory=FakeServer)
    await controller.start()
    loading = asyncio.Event()

    async def hang(self: FakeServer) -> None:
        loading.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FakeServer, "start", hang)
    controller.request_reload(ReloadRequest(expected_revision=0))
    await asyncio.wait_for(loading.wait(), 2)
    await controller.close()
    assert controller.model_state == "down"
    assert isinstance(controller.server, FakeServer) and controller.server.closed


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SORA_TEST_LLAMA_CONFIG"), reason="opt-in real model reload")
async def test_live_settings_reload_and_vision(tmp_path: Path) -> None:
    from tests.providers.test_managed_llama_server import free_port
    from tests.vision.test_capture import png

    config = LlamaServerConfig.load(Path(os.environ["SORA_TEST_LLAMA_CONFIG"]))
    initial = AppSettings.model_validate(
        {
            "dialogue": {"backend": "managed-llama"},
            "llama": {**config.model_dump(), "port": free_port()},
        }
    )
    controller = AppSettingsController(tmp_path, initial)
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        app_settings=controller,
    )
    api = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="settings-live-token"))
    try:
        await controller.start()
        assert controller.model_state == "ready", controller.last_error
        assert controller.server is not None
        old_key = controller.server.api_key
        await runtime.start()
        await api.start()
        headers = {"Authorization": "Bearer settings-live-token"}
        base = f"http://127.0.0.1:{api.actual_port}"
        async with httpx.AsyncClient(timeout=100, trust_env=False) as client:
            saved = await client.post(
                base + "/api/v1/settings",
                headers=headers,
                json={
                    "version": 2,
                    "expected_revision": 0,
                    "changes": {
                        "llama.context_size": 4096,
                        "llama.flash_attn": "on",
                        "llama.cache_type_k": "q8_0",
                        "llama.cache_type_v": "q8_0",
                    },
                },
            )
            assert saved.status_code == 200, saved.text
            loaded = await client.post(
                base + "/api/v1/model/reload", headers=headers, json={"expected_revision": 1}
            )
            assert loaded.status_code == 202, loaded.text
            assert controller.task is not None
            await controller.task
            assert controller.model_state == "ready", controller.last_error
            assert not controller.rollback_applied, controller.last_error
            assert controller.server.api_key != old_key
            denied = await client.get(
                controller.server.base_url + "/models",
                headers={"Authorization": f"Bearer {old_key}"},
            )
            assert denied.status_code == 401
            for color, rgba in (("red", (255, 0, 0, 255)), ("blue", (0, 0, 255, 255))):
                target = tmp_path / "image.png"
                target.write_bytes(png(256, 256, rgba))
                response = await client.post(
                    base + "/api/v1/dialogue",
                    headers=headers,
                    json={
                        "content": "Name the dominant color in this image in one word.",
                        "file_paths": [str(target)],
                    },
                )
                assert response.status_code == 201, response.text
                answer = response.json()["response"]
                print(f"Reloaded model, flash on / q8 KV / 4096 context: {answer}")
                assert color in answer.lower()
        assert not controller.projection()["model_reload_required"]
        assert controller.server.api_key not in controller.store.path.read_text()
    finally:
        await api.close()
        await runtime.close()
