"""Canonical per-model descriptions, preserved migration and bounded companion discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.companion_call import Delegate, ListAgents
from sora.runtime.agent_catalogue import AgentCatalogue
from sora.runtime.agent_preferences import AgentPreferences
from sora.runtime.app_settings import (
    MAX_SETTINGS_BYTES,
    AppSettings,
    AppSettingsController,
    AppSettingsStore,
    SettingsConflict,
    SettingsEdit,
)
from sora.runtime.delegation_catalogue import DelegationCatalogue
from sora.runtime.service import RuntimeConfig, SoraRuntime
from tests.runtime.test_agent_catalogue import CatalogueProvider
from tests.runtime.test_companion_calls import Caller


def save(settings: AppSettingsController, **changes: Any) -> dict[str, Any]:
    return settings.save(
        SettingsEdit(
            version=9,
            expected_revision=settings.saved.revision,
            changes=changes,
        )
    )


def test_v8_migration_preserves_bytes_disables_paths_and_legacy_purpose(tmp_path: Path) -> None:
    original = AppSettings().model_dump(mode="json")
    original["version"] = 8
    for entry in original["agents"].values():
        del entry["model_choices"]
    original["agents"]["codex"].update(
        preferred_model="opaque:model",
        model_purpose="Small coding tasks",
        enabled=False,
        project_root=str(tmp_path),
        workspace_mode="isolated",
        base_ref="main",
    )
    original["agents"]["hermes"]["model_purpose"] = "Fallback with no selected model"
    original["local_companion"]["desktop_capture"] = False
    path = tmp_path / "settings.json"
    raw = json.dumps(original)
    path.write_text(raw)
    migrated = AppSettingsStore(path).load()
    assert migrated.version == 9 and not migrated.agents.codex.enabled
    assert not migrated.local_companion.desktop_capture
    assert migrated.agents.codex.project_root == str(tmp_path)
    assert migrated.agents.codex.workspace_mode == "isolated"
    assert migrated.agents.codex.base_ref == "main"
    assert migrated.agents.codex.model_choices[0].id == "opaque:model"
    assert migrated.agents.codex.model_choices[0].purpose == "Small coding tasks"
    assert migrated.agents.hermes.model_purpose == "Fallback with no selected model"
    assert next(tmp_path.glob("settings.v8-*.json")).read_text() == raw
    assert json.loads(path.read_text())["version"] == 9


@pytest.mark.parametrize(
    "rows",
    [
        [{"id": "m", "purpose": "x"}, {"id": "m", "purpose": "y"}],
        [{"id": "two words", "purpose": "x"}],
        [{"id": "m", "purpose": "x" * 501}],
        [{"id": "m", "purpose": "x", "authorized_by": "owner"}],
        [{"id": f"m{index}"} for index in range(65)],
        "not an array",
    ],
)
def test_bad_rows_are_atomic_and_do_not_touch_settings(tmp_path: Path, rows: Any) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    before = settings.store.path.read_bytes()
    with pytest.raises(ValueError):
        save(settings, **{"agents.codex.model_choices": rows})
    assert settings.saved.revision == 0 and settings.store.path.read_bytes() == before


def test_live_save_restart_hand_edits_conflicts_and_large_store(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    rows = [{"id": f"m{index}", "purpose": "Research " * 50} for index in range(64)]
    view = save(settings, **{"agents.codex.model_choices": rows})
    field = next(item for item in view["fields"] if item["key"] == "agents.codex.model_choices")
    assert field["type"] == "agent-model-purposes" and field["tier"] == "live"
    assert field["active_value"] == rows and not field["pending"]
    assert not view["restart_required"] and settings.saved.delegation_epoch == 0
    assert 16_384 < settings.store.path.stat().st_size < MAX_SETTINGS_BYTES
    restarted = AppSettingsController(tmp_path, AppSettings())
    assert restarted.saved.agents.codex.model_choices == settings.saved.agents.codex.model_choices
    raw = json.loads(settings.store.path.read_text())
    raw["agents"]["codex"]["model_choices"][0]["purpose"] = "Edited on disk"
    settings.store.path.write_text(json.dumps(raw))
    with pytest.raises(SettingsConflict):
        save(settings, **{"agents.codex.model_choices": []})
    settings.refresh()
    assert settings.active.agents.codex.model_choices[0].purpose == "Edited on disk"
    assert settings.saved.revision == 2 and settings.saved.delegation_epoch == 0
    save(settings, **{"agents.codex.model_choices": []})
    assert not settings.active.agents.codex.model_choices


def test_disk_revision_cannot_rollback_even_without_content_change(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    save(settings, **{"agents.codex.model_choices": [{"id": "m", "purpose": "Docs"}]})
    raw = json.loads(settings.store.path.read_text())
    raw["revision"] = 0
    settings.store.path.write_text(json.dumps(raw))
    settings.refresh()
    assert settings.saved.revision == 2 and settings.saved.delegation_epoch == 0
    assert json.loads(settings.store.path.read_text())["revision"] == 2


def test_oversized_store_is_bounded_and_not_read(tmp_path: Path) -> None:
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_SETTINGS_BYTES + 1))
    store = AppSettingsStore(path)
    assert store.digest.startswith("oversized:")
    with pytest.raises(ValueError, match="256 KiB"):
        store.load()


def test_incomplete_current_settings_are_not_silently_migrated(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    payload = json.loads(settings.store.path.read_text())
    del payload["agents"]["hermes"]["model_choices"]
    settings.store.path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="complete preferences"):
        AppSettingsStore(settings.store.path).load()
    # Recovery is the previous valid settings, not a reset of effective access.
    recovered = AppSettingsController(tmp_path, AppSettings())
    assert recovered.disk_error and recovered.saved.agents == settings.saved.agents


@pytest.mark.asyncio
async def test_live_catalogue_purposes_override_metadata_and_remain_separate_from_access() -> None:
    preferences = AgentPreferences.model_validate(
        {
            "codex": {
                "preferred_model": "opaque/provider:model",
                "model_purpose": "Legacy default fallback",
                "model_choices": [
                    {"id": "opaque/provider:model", "purpose": "Cheap specialist research"},
                    {"id": "configured-unverified", "purpose": "Owner planned model"},
                ],
            }
        }
    )
    provider = CatalogueProvider("codex-app-server")
    catalogue = AgentCatalogue({"codex": provider}, preferences=lambda: preferences)
    before = await catalogue.snapshot()
    assert (
        provider.calls == 0
        and before["providers"][0]["models"][0]["state"] == "configured_not_checked"
    )
    await catalogue.refresh()
    refreshed = (await catalogue.snapshot())["providers"][0]
    one, two = refreshed["models"]
    assert (
        one["purpose"] == "Cheap specialist research" and one["purpose_source"] == "owner_shortlist"
    )
    assert one["description"] == "Purpose from provider" and one["state"] == "provider_listed"
    assert two["state"] == "configured_not_checked" and not two["execution_verified"]
    references = await DelegationCatalogue.create(catalogue)
    references.preview()
    assert references.rows["codex"]["models"][0]["purpose"] == "Cheap specialist research"
    with pytest.raises(ValueError):
        references.select(Delegate(op="delegate", task="x", model="m2"))
    page = references.list_agents(ListAgents(op="list_agents"))
    selected = references.select(Delegate(op="delegate", task="x", model=page["models"][1]["ref"]))
    assert selected.model == "configured-unverified" and selected.provider == "codex"
    assert provider.calls == 1 and not provider.started_runs


@pytest.mark.asyncio
async def test_purpose_change_does_not_probe_and_empty_removes_override() -> None:
    preferences = AgentPreferences()
    provider = CatalogueProvider("hermes-acp")
    catalogue = AgentCatalogue({"hermes": provider}, preferences=lambda: preferences)
    await catalogue.refresh()
    preferences = AgentPreferences.model_validate(
        {
            "hermes": {
                "model_choices": [{"id": "opaque/provider:model", "purpose": "New live purpose"}],
            }
        }
    )
    assert (await catalogue.snapshot())["providers"][0]["models"][0][
        "purpose"
    ] == "New live purpose"
    preferences = AgentPreferences()
    row = (await catalogue.snapshot())["providers"][0]["models"][0]
    assert row["purpose"] == row["description"] and not row["shortlisted"]
    assert provider.calls == 1


@pytest.mark.asyncio
async def test_literal_discovery_filter_binds_cursor_and_reaches_full_shortlist() -> None:
    preferences = AgentPreferences.model_validate(
        {
            "codex": {
                "model_choices": [
                    {"id": f"id-{index}", "purpose": "Cheap research"} for index in range(64)
                ],
            }
        }
    )
    provider = CatalogueProvider("codex-app-server")
    catalogue = AgentCatalogue({"codex": provider}, preferences=lambda: preferences)
    references = await DelegationCatalogue.create(catalogue)
    found = references.list_agents(ListAgents(op="list_agents", query="id-63"))
    assert len(found["models"]) == 1 and found["continuation"] is None
    selected = references.select(
        Delegate(
            op="delegate",
            task="Explain",
            model=found["models"][0]["ref"],
        )
    )
    assert selected.model == "id-63"
    first = references.list_agents(ListAgents(op="list_agents", query="cheap"))
    assert len(first["models"]) == 8 and first["continuation"]
    with pytest.raises(ValueError, match="provider/query"):
        references.list_agents(
            ListAgents(op="list_agents", query="another", cursor=first["continuation"])
        )
    next_page = references.list_agents(
        ListAgents(op="list_agents", query="CHEAP", cursor=first["continuation"])
    )
    assert (
        len(next_page["models"]) == 8 and next_page["models"][0]["ref"] != first["models"][0]["ref"]
    )
    assert provider.calls == 0 and not provider.started_runs


@pytest.mark.asyncio
async def test_actual_owner_http_save_catalogue_and_companion_selection(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    provider = CatalogueProvider("codex-app-server")
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity"
        ),
        providers={"codex": provider},
        app_settings=settings,
    )
    await runtime.start()
    server = SoraApiServer(
        runtime, ApiServerConfig(port=0, auth_token="model-purposes-fixture-token")
    )
    await server.start()
    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token="model-purposes-fixture-token",
    )
    try:
        status, view = await client._request_dict(
            "POST",
            "/api/v1/settings",
            body={
                "version": 9,
                "expected_revision": 0,
                "changes": {
                    "agents.codex.model_choices": [
                        {"id": "fixture-docs", "purpose": "Cheap documentation"},
                        {"id": "fixture-research", "purpose": "Specialist research"},
                    ],
                    "perception.desktop_context": False,
                },
            },
        )
        assert status == 200 and view["settings_version"] == 9 and view["settings_revision"] == 1
        status, catalogue = await client._request_dict("GET", "/api/v1/agents/catalogue")
        assert (
            status == 200
            and catalogue["providers"][0]["models"][1]["purpose"] == "Specialist research"
        )
        assert not provider.calls and not provider.started_runs
        settings.provider = Caller(
            {"op": "list_agents", "query": "research"},
            {"op": "delegate", "task": "Explain the research fixture", "model": "m2"},
        )
        status, reply = await client._request_dict(
            "POST",
            "/api/v1/dialogue",
            body={
                "content": "Ask Codex to explain research methods",
                "request_id": "purpose-selection",
            },
        )
        assert status == 201 and "queued" in reply["response"]
        task = (await runtime.runtime_repository.list_tasks())[0]
        assert task.requested_model == "fixture-research" and task.requested_backend == "codex"
        await runtime.wait_for_task(task.task_id)
        assert provider._requests[task.active_run_id or ""].model == "fixture-research"
        assert provider.calls == 0
    finally:
        await server.close()
        await runtime.close()
