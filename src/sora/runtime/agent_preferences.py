"""Canonical specialist preferences, not a second provider configuration store."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from sora.contracts.base import StrictModel
from sora.contracts.models import ModelId, ReasoningEffort, WorkspaceMode
from sora.routing.agent_names import (
    CUSTOM_SLOTS,
    DEFAULT_DIRECTORY,
    AgentDirectory,
    parse_aliases,
)

# Default usage descriptions. SORA reads these when she decides which colleague to ask, so they
# say what each agent is for. The owner may overwrite any of them in Settings.
DEFAULT_PURPOSES = {
    "codex": "Coding, repository changes, tests and specialist reasoning through Codex.",
    "hermes": "General specialist tasks using Hermes' own native tools and integrations.",
    "antigravity": "Research, planning and project work through Antigravity's native tools.",
    "claude": (
        "Careful coding, code review, debugging, long documents and in-depth research "
        "through Claude Code."
    ),
    "custom": (
        "A custom agent the owner added. Ask it when the owner names it, or when its "
        "description fits the task better than the other agents."
    ),
}


class AgentModelPurpose(StrictModel):
    id: ModelId
    purpose: str = Field(default="", max_length=500)


class AgentPreference(StrictModel):
    enabled: StrictBool = True
    purpose: str = Field(default="", max_length=500)
    preferred_model: str = Field(default="", max_length=256, pattern=r"^(?:[^\s\x00-\x1f\x7f]+)?$")
    preferred_effort: Literal["configured"] | ReasoningEffort = "configured"
    model_purpose: str = Field(default="", max_length=500)
    model_choices: tuple[AgentModelPurpose, ...] = Field(default=(), max_length=64)
    project_root: str = Field(default="", max_length=4096)
    workspace_mode: WorkspaceMode = "direct"
    base_ref: str = Field(default="HEAD", min_length=1, max_length=256)

    @model_validator(mode="after")
    def unique_models(self) -> AgentPreference:
        ids = [entry.id for entry in self.model_choices]
        if len(set(ids)) != len(ids):
            raise ValueError("Each exact model ID may appear only once in an agent shortlist")
        return self

class CustomEndpoint(StrictModel):
    """An owner-added agent reached over an OpenAI-compatible API on this machine."""

    enabled: StrictBool = False
    nickname: str = Field(default="", max_length=40)
    spoken_aliases: str = Field(default="", max_length=400)
    port: int = Field(default=0, ge=0, le=65535)
    default_model: str = Field(
        default="", max_length=256, pattern=r"^(?:[^\s\x00-\x1f\x7f]+)?$",
    )
    purpose: str = Field(default=DEFAULT_PURPOSES["custom"], max_length=500)

    @model_validator(mode="after")
    def usable_when_enabled(self) -> CustomEndpoint:
        self.aliases()  # Invalid aliases are rejected even while the slot is off.
        if self.enabled and (not self.nickname.strip() or self.port == 0):
            raise ValueError("An enabled custom agent needs a nickname and a port")
        return self

    def aliases(self) -> tuple[str, ...]:
        return parse_aliases(self.spoken_aliases)


def _builtin(name: str) -> AgentPreference:
    return AgentPreference(purpose=DEFAULT_PURPOSES[name])


class AgentPreferences(StrictModel):
    codex: AgentPreference = Field(default_factory=lambda: _builtin("codex"))
    hermes: AgentPreference = Field(default_factory=lambda: _builtin("hermes"))
    antigravity: AgentPreference = Field(default_factory=lambda: _builtin("antigravity"))
    claude: AgentPreference = Field(default_factory=lambda: _builtin("claude"))
    custom_1: CustomEndpoint = Field(default_factory=CustomEndpoint)
    custom_2: CustomEndpoint = Field(default_factory=CustomEndpoint)
    custom_3: CustomEndpoint = Field(default_factory=CustomEndpoint)
    custom_4: CustomEndpoint = Field(default_factory=CustomEndpoint)

    @model_validator(mode="after")
    def harness_efforts(self) -> AgentPreferences:
        if self.hermes.preferred_effort != "configured":
            raise ValueError("Hermes does not expose per-run reasoning effort")
        if self.claude.preferred_effort != "configured":
            raise ValueError("Claude per-run reasoning effort is not mapped yet")
        effort = self.antigravity.preferred_effort
        if effort not in {"configured", "low", "medium", "high", "max"}:
            raise ValueError("Antigravity effort must be configured, low, medium, high or max")
        tier = self.antigravity.preferred_model.rsplit("-", 1)[-1]
        if tier in {"low", "medium", "high", "max"} and effort not in {"configured", tier}:
            raise ValueError("The Antigravity model already specifies a different effort tier")
        self.directory()  # Nicknames and aliases must not clash with each other or built-ins.
        return self

    def custom_endpoints(self) -> dict[str, CustomEndpoint]:
        """Custom slots by routing key (``custom-1``…)."""
        return {slot: getattr(self, slot.replace("-", "_")) for slot in CUSTOM_SLOTS}

    def directory(self) -> AgentDirectory:
        """Agent names, including the nicknames of enabled custom endpoints."""
        return DEFAULT_DIRECTORY.with_custom([
            (key, endpoint.nickname.strip(), endpoint.aliases())
            for key, endpoint in self.custom_endpoints().items() if endpoint.enabled
        ])

    def for_provider(self, provider: str) -> AgentPreference | None:
        name = {
            "codex-app-server": "codex", "hermes-acp": "hermes", "claude-code": "claude",
        }.get(provider, provider)
        if name in {"codex", "hermes", "antigravity", "claude"}:
            return getattr(self, name, None)
        endpoint = self.custom_endpoints().get(name)
        if endpoint is None:
            return None
        # A custom endpoint offers its usage description and default model to the shared
        # catalogue; it has no shortlist, effort or project of its own.
        return AgentPreference(
            enabled=endpoint.enabled, purpose=endpoint.purpose,
            preferred_model=endpoint.default_model,
        )

    def enabled_state(self) -> tuple[bool, ...]:
        return (
            self.codex.enabled, self.hermes.enabled, self.antigravity.enabled,
            self.claude.enabled,
            *(endpoint.enabled for endpoint in self.custom_endpoints().values()),
        )
