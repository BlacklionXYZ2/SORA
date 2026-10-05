from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sora.contracts.models import ProviderCapabilities, TaskStatus
from sora.runtime.agent_preferences import AgentPreferences
from sora.runtime.app_settings import (
    AppSettings,
    AppSettingsController,
    AppSettingsStore,
    SettingsEdit,
)
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError
from tests.runtime.test_agent_catalogue import CatalogueProvider
from tests.runtime.test_delegation_policy import HeldProvider


@pytest.fixture(autouse=True)
def owner_scope():  # type: ignore[no-untyped-def]
    with owner_local_scope():
        yield


def save(controller: AppSettingsController, **changes: object) -> None:
    controller.save(SettingsEdit(
        version=8, expected_revision=controller.saved.revision, changes=changes,
    ))


def test_v6_migration_preserves_original_and_voice(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    old = AppSettings().model_dump(mode="json")
    old["version"] = 6
    del old["agents"]
    old["voice"]["speech_speed"] = 1.1
    original = json.dumps(old)
    path.write_text(original, encoding="utf-8")
    settings = AppSettingsStore(path).load()
    assert settings.version == 9 and settings.voice.speech_speed == 1.1
    assert next(tmp_path.glob("settings.v6-*.json")).read_text() == original
    assert json.loads(path.read_text())["agents"]["hermes"]["enabled"] is True


@pytest.mark.parametrize("changes", [
    {"agents.hermes.preferred_effort": "low"},
    {"agents.codex.preferred_model": "two words"},
    {"agents.antigravity.preferred_effort": "ultra"},
    {"agents.antigravity.preferred_model": "gemini-3.8-flash-low",
     "agents.antigravity.preferred_effort": "high"},
])
def test_invalid_preferences_do_not_change_disk(tmp_path: Path, changes: dict[str, object]) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    before = controller.store.path.read_bytes()
    with pytest.raises(ValueError):
        save(controller, **changes)
    assert controller.store.path.read_bytes() == before and controller.saved.revision == 0


def test_preferences_live_restart_and_revocation_epoch(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    save(controller, **{
        "agents.codex.preferred_model": "opaque/provider:model",
        "agents.codex.preferred_effort": "low",
        "agents.codex.model_purpose": "Small cheap documentation tasks",
    })
    assert controller.active.agents.codex.preferred_model == "opaque/provider:model"
    assert controller.saved.delegation_epoch == 0 and controller.policy_epoch == 0
    assert not controller.projection()["restart_required"]
    restored = AppSettingsController(tmp_path, AppSettings())
    assert restored.active.agents == controller.active.agents
    save(controller, **{"agents.codex.enabled": False})
    assert controller.saved.delegation_epoch == 1 and controller.policy_epoch == 1
    save(controller, **{"agents.codex.enabled": True})
    assert controller.saved.delegation_epoch == 2


def test_incomplete_v7_agent_preferences_fail_closed(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    payload = json.loads(controller.store.path.read_text())
    del payload["agents"]["hermes"]["enabled"]
    controller.store.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="complete preferences"):
        AppSettingsStore(controller.store.path).load()


@pytest.mark.asyncio
async def test_preferences_pin_new_and_planned_tasks_not_existing_runs(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    save(controller, **{
        "agents.codex.preferred_model": "opaque/provider:model",
        "agents.codex.preferred_effort": "low",
    })
    provider = CatalogueProvider("codex-app-server")
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity",
        ),
        providers={"codex": provider}, app_settings=controller,
    )
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Inspect", explicit_provider="codex")
        save(controller, **{"agents.codex.preferred_model": "new-model"})
        assert (await runtime.wait_for_task(receipt.task.task_id)).status is TaskStatus.COMPLETED
        assert provider._requests[receipt.run.run_id].model == "opaque/provider:model"
        assert provider._requests[receipt.run.run_id].reasoning_effort == "low"
        override = await runtime.submit_task(
            "Inspect", explicit_provider="codex", explicit_model="m",
        )
        assert override.task.requested_model == "m" and override.task.requested_effort is None
        await runtime.wait_for_task(override.task.task_id)
        planned = await runtime.plan_task("Inspect this project")
        started = await runtime.start_planned_task(planned.task_id, explicit_provider="codex")
        assert started.requested_model == "new-model" and started.requested_effort == "low"
        await runtime.wait_for_task(started.task_id)
        save(controller, **{"agents.codex.enabled": False})
        with pytest.raises(OperationAuthorizationError, match="disabled"):
            await runtime.submit_task("Do not launch", explicit_provider="codex")
        with pytest.raises(OperationAuthorizationError, match="disabled"):
            await runtime.retry(receipt.task.task_id)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_catalogue_projects_preferences_without_discovery() -> None:
    from sora.runtime.agent_catalogue import AgentCatalogue

    preferences = AgentPreferences.model_validate({"hermes": {
        "model_purpose": "Local tools and low-cost research",
        "preferred_model": "openai-codex:gpt-6-luna", "enabled": False,
    }})
    provider = CatalogueProvider("hermes-acp")
    catalogue = AgentCatalogue({"hermes": provider}, preferences=lambda: preferences)
    snapshot = await catalogue.snapshot()
    entry = snapshot["providers"][0]
    assert entry["enabled"] is False
    assert entry["effective_default_model"] == "openai-codex:gpt-6-luna"
    assert entry["model_purpose"] == "Local tools and low-cost research"
    assert entry["state"] == "not_checked" and provider.calls == 0


class HeldHermes(HeldProvider):
    async def capabilities(self) -> ProviderCapabilities:
        return (await super().capabilities()).model_copy(update={"provider": "hermes-acp"})


@pytest.mark.asyncio
async def test_agent_off_on_revokes_active_and_queued_local_runs(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    provider = HeldHermes()
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity",
            worker_count=1,
        ),
        providers={"hermes": provider}, app_settings=controller,
    )
    await runtime.start()
    try:
        first = await runtime.submit_task("Inspect", explicit_provider="hermes")
        await asyncio.wait_for(provider.started.wait(), 2)
        second = await runtime.submit_task("Queued inspect", explicit_provider="hermes")
        save(controller, **{"agents.hermes.enabled": False})
        save(controller, **{"agents.hermes.enabled": True})
        reports = await asyncio.gather(
            runtime.wait_for_task(first.task.task_id), runtime.wait_for_task(second.task.task_id),
        )
        assert all(report.status is TaskStatus.CANCELLED for report in reports)
        assert provider.start_count == 1 and controller.saved.delegation_epoch == 2
    finally:
        await runtime.close()
