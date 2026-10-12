"""Settings v10: Claude, custom agents and the usage descriptions SORA chooses agents by."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from sora.contracts.companion_call import Delegate
from sora.contracts.models import ProviderCapabilities
from sora.runtime.agent_catalogue import AgentCatalogue
from sora.runtime.agent_preferences import DEFAULT_PURPOSES, AgentPreferences, CustomEndpoint
from sora.runtime.app_settings import FIELDS, AppSettings, AppSettingsStore
from sora.runtime.delegation_catalogue import DelegationCatalogue


class FakeAgent:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.provider, display_name="Harness label")


def test_every_agent_has_a_default_usage_description() -> None:
    agents = AgentPreferences()
    assert agents.claude.purpose == DEFAULT_PURPOSES["claude"]
    for endpoint in agents.custom_endpoints().values():
        assert endpoint.purpose == DEFAULT_PURPOSES["custom"] and not endpoint.enabled
    for key in ("codex", "hermes", "antigravity", "claude"):
        assert getattr(agents, key).purpose == DEFAULT_PURPOSES[key]


def test_v9_settings_migrate_to_v10_keeping_owner_descriptions(tmp_path: Path) -> None:
    original = AppSettings().model_dump(mode="json")
    original["version"] = 9
    for name in ("claude", "custom_1", "custom_2", "custom_3", "custom_4"):
        del original["agents"][name]
    original["agents"]["codex"]["purpose"] = "Only for my Rust projects."
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(original))
    migrated = AppSettingsStore(path).load()
    assert migrated.version == 10
    assert migrated.agents.codex.purpose == "Only for my Rust projects."
    assert migrated.agents.claude.purpose == DEFAULT_PURPOSES["claude"]
    assert not migrated.agents.custom_1.enabled
    assert json.loads(next(tmp_path.glob("settings.v9-*.json")).read_text()) == original


def test_custom_agent_validation() -> None:
    with pytest.raises(ValidationError, match="needs a port"):
        CustomEndpoint(enabled=True, nickname="Pip")
    with pytest.raises(ValidationError, match="Spoken alias"):
        CustomEndpoint(spoken_aliases="ok, <bad>")
    with pytest.raises(ValidationError, match="already names another agent"):
        AgentPreferences(custom_1=CustomEndpoint(enabled=True, nickname="Cody", port=9000))
    with pytest.raises(ValidationError, match="already names another agent"):
        AgentPreferences(
            custom_1=CustomEndpoint(enabled=True, nickname="Pip", port=9000),
            custom_2=CustomEndpoint(enabled=True, nickname="Juniper", port=9001,
                                    spoken_aliases="pip"),
        )
    with pytest.raises(ValidationError, match="Claude per-run reasoning effort"):
        AgentPreferences.model_validate({"claude": {"preferred_effort": "high"}})


def test_custom_agent_fields_are_labelled_and_apply_at_next_start() -> None:
    fields = {item["key"]: item for item in FIELDS}
    nickname = fields["agents.custom_2.nickname"]
    assert nickname["group"] == "Agents · Custom agent 2"
    assert nickname["tier"] == "next_boot" and nickname["type"] == "string"
    assert fields["agents.custom_2.purpose"]["tier"] == "live"
    assert fields["agents.custom_2.port"]["type"] == "int"
    assert fields["agents.claude.preferred_effort"]["choices"] == ["configured"]
    assert fields["agents.claude.purpose"]["label"].startswith("Usage description")


@pytest.mark.asyncio
async def test_catalogue_shows_names_descriptions_and_custom_agents() -> None:
    agents = AgentPreferences(
        codex=AgentPreferences().codex.model_copy(update={"purpose": "Owner's own words."}),
        custom_1=CustomEndpoint(enabled=True, nickname="Pip", port=9000, spoken_aliases="pippa",
                                default_model="local-coder", purpose="Fast local drafts."),
    )
    providers: dict[str, Any] = {
        "codex": FakeAgent("codex-app-server"), "antigravity": FakeAgent("antigravity"),
        "claude": FakeAgent("claude-code"), "custom-1": FakeAgent("custom-1"),
    }
    catalogue = AgentCatalogue(
        providers,
        preferences=lambda: agents,
        agent_names=agents.directory,
    )
    snapshot = await catalogue.snapshot()
    rows = {entry["provider"]: entry for entry in snapshot["providers"]}
    assert rows["codex-app-server"]["display_name"] == "Cody"
    assert rows["codex-app-server"]["purpose"] == "Owner's own words."
    assert rows["antigravity"]["display_name"] == "Aggie"
    assert rows["claude-code"]["display_name"] == "Claude"
    assert rows["custom-1"]["display_name"] == "Pip"
    assert rows["custom-1"]["spoken_aliases"] == ["pippa"]
    assert rows["custom-1"]["effective_default_model"] == "local-coder"

    references = DelegationCatalogue(snapshot)
    preview = {row["provider"]: row for row in references.preview()["agents"]}
    assert set(preview) == {"codex", "antigravity", "claude", "custom-1"}
    assert preview["custom-1"]["name"] == "Pip"
    assert preview["custom-1"]["purpose"] == "Fast local drafts."
    assert references.select(Delegate(op="delegate", task="x", provider="claude")).provider == (
        "claude"
    )
    assert references.select(
        Delegate(op="delegate", task="x", provider="custom-1"),
    ).provider == "custom-1"


@pytest.mark.asyncio
async def test_disabled_custom_agent_is_not_offered() -> None:
    agents = AgentPreferences()
    providers: dict[str, Any] = {"custom-3": FakeAgent("custom-3")}
    catalogue = AgentCatalogue(
        providers,
        preferences=lambda: agents, agent_names=agents.directory,
    )
    references = DelegationCatalogue(await catalogue.snapshot())
    assert references.preview()["agents"] == []
    with pytest.raises(ValueError, match="disabled or unavailable"):
        references.select(Delegate(op="delegate", task="x", provider="custom-3"))


@pytest.mark.asyncio
async def test_agent_roster_and_project_references_survive_small_model_mistakes() -> None:
    agents = AgentPreferences()
    agents = agents.model_copy(update={"custom_1": agents.custom_1.model_copy(update={
        "enabled": True, "nickname": "Pip", "protocol": "openai-compatible", "port": 18995,
        "purpose": "Quick local checks.",
    })})
    providers: dict[str, Any] = {"custom-1": FakeAgent("custom-1")}
    catalogue = AgentCatalogue(providers, preferences=lambda: agents, agent_names=agents.directory)
    references = DelegationCatalogue(await catalogue.snapshot())
    # The roster names the nickname and its provider ID, outside the trimmed observations.
    assert "Pip = provider custom-1: Quick local checks." in references.roster()
    # A chat-only custom agent ignores any project, invented or not.
    assert references.select(Delegate(op="delegate", task="x", provider="custom-1",
                                      project="weekend-trip")).project is None
    # ...and an invented model reference falls back to its configured default.
    assert references.select(Delegate(op="delegate", task="x", provider="custom-1",
                                      model="pip-large")).model is None
    # The agent's own name in the model field selects that agent with its default model.
    chosen = references.select(Delegate(op="delegate", task="x", model="Pip"))
    assert (chosen.provider, chosen.model) == ("custom-1", None)
    with pytest.raises(ValueError, match="Unknown or stale model"):
        references.select(Delegate(op="delegate", task="x", model="pip-large"))
    # With no project folder anywhere, an invented reference means "no project" (live,
    # 2026-10-10)...
    assert references.select(Delegate(op="delegate", task="x",
                                      project="weekend-trip")).project is None
    # ...but once projects exist, a reference Core never issued is still refused.
    references.projects["p1"] = ("C:/projects/sora", "direct")
    with pytest.raises(ValueError, match="stale project reference"):
        references.select(Delegate(op="delegate", task="x", project="weekend-trip"))
    assert references.select(Delegate(op="delegate", task="x", project="p1")).project == (
        "C:/projects/sora")
