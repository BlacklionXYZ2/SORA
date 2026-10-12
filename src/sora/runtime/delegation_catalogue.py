"""Turn-local opaque references over existing configured-agent metadata, not a new store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sora.contracts.companion_call import Delegate, ListAgents
from sora.providers.base import ProviderLaunchError
from sora.routing.agent_names import CUSTOM_SLOTS
from sora.runtime.agent_catalogue import AgentCatalogue

_HARNESS = {
    "codex-app-server": "codex", "hermes-acp": "hermes", "antigravity": "antigravity",
    "claude-code": "claude", **{slot: slot for slot in CUSTOM_SLOTS},
}


@dataclass(frozen=True)
class DelegationSelection:
    provider: str | None
    model: str | None
    project: str | None
    mode: str | None


class DelegationCatalogue:
    def __init__(self, snapshot: dict[str, Any]):
        self.models: dict[str, tuple[str, str]] = {}
        self.projects: dict[str, tuple[str, str]] = {}
        self.rows: dict[str, dict[str, Any]] = {}
        self.cursors: dict[str, tuple[str, str, int]] = {}
        self.exposed_models: set[str] = set()
        for entry in snapshot["providers"]:
            provider = _HARNESS.get(entry["provider"])
            if provider is None or not entry["enabled"]:
                continue
            project = None
            if entry["project_root"]:
                project = "p" + str(len(self.projects) + 1)
                self.projects[project] = entry["project_root"], entry["workspace_mode"]
            models = []
            default = entry["effective_default_model"]
            listed = {item["id"]: item for item in entry["models"]}
            ids = list(dict.fromkeys([*([default] if default else []), *listed]))
            for model_id in ids:
                ref = "m" + str(len(self.models) + 1)
                self.models[ref] = provider, model_id
                item = listed.get(model_id, {})
                models.append({
                    "ref": ref, "name": item.get("display_name", model_id),
                    "purpose": (item["purpose"] if "purpose" in item else
                                entry["model_purpose"] if model_id == entry["preferred_model"]
                                and entry["model_purpose"] else item.get("description", ""))[:240],
                    "shortlisted": item.get("shortlisted", False),
                    "state": item.get("state", "configured_not_checked"),
                    "execution_verified": False,
                    "default": model_id == default,
                })
            self.rows[provider] = {
                "provider": provider, "name": entry["display_name"], "purpose": entry["purpose"],
                "project": project, "project_path": entry["project_root"],
                "mode": entry["workspace_mode"], "project_boundary": entry["project_boundary"],
                "models": models, "state": entry["state"],
            }

    @classmethod
    async def create(cls, catalogue: AgentCatalogue) -> DelegationCatalogue:
        return cls(await catalogue.snapshot())  # Never refresh/infer just because chat opened.

    def roster(self) -> str:
        """One line per enabled agent, kept outside the trimmed observations.

        Window and file observations can fill the budget, and trimming drops the oldest records
        first. Without this line a model may never learn the owner's nicknames (for example
        "Pip") and refuse to delegate to them.
        """
        def flat(value: Any, limit: int) -> str:  # one line: it shares the observations header
            return " ".join(str(value).split())[:limit]

        return "; ".join(
            f"{flat(row['name'], 40)} = provider {row['provider']}: {flat(row['purpose'], 120)}"
            for row in self.rows.values()
        )

    def preview(self) -> dict[str, Any]:
        self.exposed_models.update(
            item["ref"] for row in self.rows.values() for item in row["models"] if item["default"]
        )
        return {"agents": [
            {**row, "models": [item for item in row["models"] if item["default"]]}
            for row in self.rows.values()
        ], "notice": "Defaults only; list_agents for all provider-listed model references."}

    def list_agents(self, call: ListAgents) -> dict[str, Any]:
        provider, offset = call.provider, 0
        query = call.query.casefold()
        if call.cursor is not None:
            if call.cursor not in self.cursors:
                raise ValueError("Unknown or stale agent cursor")
            bound_provider, bound_query, offset = self.cursors[call.cursor]
            if bound_provider != provider or bound_query != query:
                raise ValueError("Agent cursor belongs to a different provider/query listing")
        rows = [row for name, row in self.rows.items() if provider in {"auto", name}]
        flattened = [(row, item) for row in rows for item in row["models"] if not query or
                     any(query in value.casefold() for value in (
                         item["name"], item["purpose"], self.models[item["ref"]][1],
                     ))]
        page = flattened[offset:offset + 8]
        entries = [{"provider": row["provider"], **item} for row, item in page]
        self.exposed_models.update(item["ref"] for item in entries)
        continuation = None
        if offset + len(page) < len(flattened):
            continuation = "a" + str(len(self.cursors) + 1)
            self.cursors[continuation] = provider, query, offset + len(page)
        return {
            "agents": [{key: value for key, value in row.items() if key != "models"}
                       for row in rows],
            "models": entries, "continuation": continuation,
            "notice": "Listed/configured, not entitlement or successful inference. No refresh run.",
        }

    def select(self, call: Delegate) -> DelegationSelection:
        provider: str | None = None if call.provider == "auto" else call.provider
        model = None
        if provider is not None and provider not in self.rows:
            raise ValueError("The selected specialist is disabled or unavailable")
        # A small model under a JSON grammar sometimes fills optional references with invented
        # text. For a chat-only custom agent that cannot mean anything: its model is the owner's
        # configured default and it has no project folder (HOW_TO_USE.md), so an unknown
        # reference falls back to that default. For every other agent an unknown reference still
        # refuses: never guess which model or folder the owner meant.
        known_model = call.model is not None and call.model in self.models \
            and call.model in self.exposed_models
        if call.model is not None and not known_model:
            # Small models put the agent's name where the model goes ("model": "Pip"). An exact
            # agent name or provider ID there selects that agent with its configured default.
            named = [row["provider"] for row in self.rows.values()
                     if call.model.strip().casefold() in {str(row["name"]).casefold(),
                                                          str(row["provider"]).casefold()}]
            if len(named) == 1 and provider in {None, named[0]}:
                provider = named[0]
                call = call.model_copy(update={"model": None})
        chat_only = provider is not None and provider in CUSTOM_SLOTS
        if call.model is not None and (known_model or not chat_only):
            pair = self.models.get(call.model)
            if pair is None or not known_model:
                raise ValueError("Unknown or stale model reference")
            if provider is not None and provider != pair[0]:
                raise ValueError("The selected model belongs to another specialist")
            provider, model = pair
        project, mode = None, None
        if call.project is not None and not chat_only and self.projects:
            pair_project = self.projects.get(call.project)
            if pair_project is None:
                raise ValueError(
                    "Unknown or stale project reference; select the project in Settings",
                )
            project, mode = pair_project
        # With no project folder configured at all, a reference can only be invented (live,
        # 2026-10-10: E4B sent "p1" and the task was refused). It means "no project", which
        # guesses nothing; a task that would write files is still asked "Which project?".
        return DelegationSelection(provider, model, project, mode)


def delegation_failure(error: Exception) -> str:
    if isinstance(error, ProviderLaunchError):
        return f"Specialist task was not queued ({error.code.value}): {error}"
    return "Specialist task was not queued: " + str(error)
