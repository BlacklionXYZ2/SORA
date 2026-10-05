"""Owner-local specialist inventory. Listing is not proof of inference entitlement."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import TypeAdapter

from sora.contracts.models import ModelId, ReasoningEffort
from sora.providers.base import ReasoningProvider
from sora.routing.agent_names import DEFAULT_DIRECTORY, AgentDirectory
from sora.runtime.agent_preferences import DEFAULT_PURPOSES, AgentPreferences

_MODEL = TypeAdapter(ModelId)
_EFFORT: TypeAdapter[ReasoningEffort] = TypeAdapter(ReasoningEffort)
_PURPOSES = {
    "codex-app-server": DEFAULT_PURPOSES["codex"],
    "hermes-acp": DEFAULT_PURPOSES["hermes"],
    "antigravity": DEFAULT_PURPOSES["antigravity"],
    "claude-code": DEFAULT_PURPOSES["claude"],
}
_OWNER_ROSTER = {
    "antigravity": ["Gemini 3.8 Flash"],
    "hermes-acp": [
        "DeepSeek v4.1 Flash",
        "ChatGPT 5.6 Luna",
        "ChatGPT 5.6 Terra",
        "ChatGPT 6 Luna",
    ],
    "codex-app-server": ["Full provider-listed ChatGPT catalogue"],
}


def validate_selection(
    provider: str | None,
    model: str | None,
    effort: str | None,
) -> tuple[str | None, ReasoningEffort | None]:
    """Require a specific route for overrides; never silently auto-route a model ID."""
    if (model is not None or effort is not None) and (not provider or provider == "auto"):
        raise ValueError("An explicit model or effort requires an explicit provider")
    return (
        _MODEL.validate_python(model, strict=True) if model is not None else None,
        _EFFORT.validate_python(effort, strict=True) if effort is not None else None,
    )


class AgentCatalogue:
    """Cached metadata with bounded, single-flight, explicit refresh; no prompts are sent."""

    def __init__(
        self, providers: Mapping[str, ReasoningProvider], *, timeout: float = 25,
        preferences: Callable[[], AgentPreferences | None] = lambda: None,
        delegation_enabled: Callable[[], bool] = lambda: True,
        agent_names: Callable[[], AgentDirectory] = lambda: DEFAULT_DIRECTORY,
    ) -> None:
        self.providers = providers
        self.agent_names = agent_names
        self.timeout = timeout
        self.preferences = preferences
        self.delegation_enabled = delegation_enabled
        self._entries: dict[str, dict[str, Any]] = {}
        self._refresh: asyncio.Task[dict[str, Any]] | None = None

    async def snapshot(self) -> dict[str, Any]:
        entries = []
        seen: set[int] = set()
        for adapter in self.providers.values():
            if id(adapter) in seen:
                continue
            seen.add(id(adapter))
            caps = await adapter.capabilities()
            entry = self._entries.get(caps.provider)
            if entry is None:
                entry = {
                    "provider": caps.provider,
                    "display_name": caps.display_name or caps.provider,
                    "purpose": _PURPOSES.get(caps.provider, "Configured specialist adapter."),
                    "owner_roster": _OWNER_ROSTER.get(caps.provider, []),
                    "state": "not_checked",
                    "checked_at": None,
                    "models": [],
                    "error": None,
                }
            entry = copy.deepcopy(entry)
            agent = self.agent_names().for_backend(caps.provider)
            # SORA's name for the colleague (Cody, Aggie…); the harness keeps its own label.
            entry["display_name"] = agent.name if agent else entry["display_name"]
            entry["harness_name"] = caps.display_name or caps.provider
            entry["spoken_aliases"] = list(agent.aliases) if agent else []
            entry["capabilities"] = caps.model_dump(mode="json")
            entry["configured_model"] = getattr(adapter, "model", None)
            entry["configured_effort"] = getattr(
                adapter,
                "reasoning_effort",
                getattr(adapter, "effort", None),
            )
            preferences = self.preferences()
            preference = preferences.for_provider(caps.provider) if preferences else None
            entry["enabled"] = self.delegation_enabled() and (
                preference.enabled if preference else True
            )
            entry["preferred_model"] = preference.preferred_model if preference else ""
            entry["preferred_effort"] = preference.preferred_effort if preference else "configured"
            entry["model_purpose"] = preference.model_purpose if preference else ""
            entry["project_root"] = preference.project_root if preference else ""
            entry["workspace_mode"] = preference.workspace_mode if preference else "direct"
            entry["base_ref"] = preference.base_ref if preference else "HEAD"
            entry["project_boundary"] = (
                "native Codex sandbox; live boundary acceptance pending"
                if caps.provider == "codex-app-server"
                else "works directly in the selected folder; Core records the diff"
                if callable(getattr(adapter, "for_project_root", None))
                else "no project folder access"
            )
            if preference:
                entry["purpose"] = preference.purpose
            entry["effective_default_model"] = (
                entry["preferred_model"] or entry["configured_model"]
            )
            entry["effective_default_effort"] = (
                entry["preferred_effort"] if entry["preferred_effort"] != "configured"
                else entry["configured_effort"]
            )
            choices = (
                {item.id: item.purpose for item in preference.model_choices} if preference else {}
            )
            entry["model_choices"] = (
                [item.model_dump(mode="json") for item in preference.model_choices]
                if preference else []
            )
            listed = {item["id"]: item for item in entry["models"]}
            order = list(dict.fromkeys([*choices, *listed]))
            entry["models"] = []
            for model in order:
                item = listed.get(model, {
                    "id": model, "display_name": model, "description": "", "efforts": [],
                    "embedded_effort": None, "default_effort": None, "input_modalities": [],
                    "hidden": False, "state": "configured_not_checked",
                    "execution_verified": False,
                })
                purpose = (choices[model] if model in choices else
                           entry["model_purpose"] if model == entry["preferred_model"]
                           and entry["model_purpose"] else item["description"])
                entry["models"].append({
                    **item, "purpose": purpose, "shortlisted": model in choices,
                    "purpose_source": "owner_shortlist" if model in choices else
                    "owner_default" if model == entry["preferred_model"]
                    and entry["model_purpose"] else "provider_metadata",
                })
            entries.append(entry)
        return {
            "schema_version": 1,
            "providers": entries,
            "notice": "Provider-listed models are not verified entitlements. No inference was run.",
            "hermes_notice": (
                "Hermes discovery creates an empty ACP session, with no prompt or MCP startup."
            ),
        }

    async def refresh(self) -> dict[str, Any]:
        if self._refresh is None or self._refresh.done():
            self._refresh = asyncio.create_task(self._refresh_all())
        # One client disconnect must not cancel metadata discovery for another client.
        return await asyncio.shield(self._refresh)

    async def close(self) -> None:
        if self._refresh is not None and not self._refresh.done():
            self._refresh.cancel()
            await asyncio.gather(self._refresh, return_exceptions=True)

    async def _refresh_all(self) -> dict[str, Any]:
        unique = {id(adapter): adapter for adapter in self.providers.values()}
        await asyncio.gather(*(self._probe(adapter) for adapter in unique.values()))
        return await self.snapshot()

    async def _probe(self, adapter: ReasoningProvider) -> None:
        caps = await adapter.capabilities()
        entry: dict[str, Any] = {
            "provider": caps.provider,
            "display_name": caps.display_name or caps.provider,
            "purpose": _PURPOSES.get(caps.provider, "Configured specialist adapter."),
            "owner_roster": _OWNER_ROSTER.get(caps.provider, []),
            "checked_at": datetime.now(UTC).isoformat(),
            "models": [],
            "error": None,
        }
        method = getattr(adapter, "available_models", None)
        if not callable(method):
            entry["state"] = "not_supported"
            entry["error"] = (
                "This adapter does not expose model discovery. Its configured default is unchanged."
            )
        else:
            try:
                async with asyncio.timeout(self.timeout):
                    raw = await method()
                if not isinstance(raw, (list, tuple)) or len(raw) > 2_000:
                    raise ValueError("Invalid catalogue size")
                seen: set[str] = set()
                for item in raw:
                    if not isinstance(item, dict):
                        raise ValueError("Invalid model entry")
                    model = _MODEL.validate_python(item.get("model"), strict=True)
                    if model in seen:
                        continue
                    seen.add(model)
                    efforts = []
                    for choice in item.get("supportedReasoningEfforts", []):
                        value = (
                            choice.get("reasoningEffort") if isinstance(choice, dict) else choice
                        )
                        if value in {
                            "none",
                            "minimal",
                            "low",
                            "medium",
                            "high",
                            "xhigh",
                            "max",
                            "ultra",
                        }:
                            efforts.append(value)
                    tier = model.rsplit("-", 1)[-1]
                    embedded = (
                        tier
                        if caps.provider == "antigravity"
                        and tier
                        in {
                            "low",
                            "medium",
                            "high",
                            "max",
                        }
                        else None
                    )
                    if caps.provider == "antigravity" and not embedded:
                        efforts = ["low", "medium", "high", "max"]
                    entry["models"].append(
                        {
                            "id": model,
                            "display_name": str(item.get("displayName") or model)[:256],
                            "description": str(item.get("description") or "")[:2_000],
                            "efforts": efforts,
                            "embedded_effort": embedded,
                            "default_effort": item.get("defaultReasoningEffort"),
                            "input_modalities": item.get("inputModalities", []),
                            "hidden": item.get("hidden") is True,
                            "state": "provider_listed",
                            "execution_verified": False,
                        }
                    )
                entry["state"] = "listed"
            except Exception as exc:
                entry["models"] = []
                entry["state"] = "unavailable"
                # Never echo backend errors/configuration which can contain credentials.
                entry["error"] = (
                    f"Model discovery failed ({type(exc).__name__}); no model was substituted."
                )
        self._entries[caps.provider] = entry
