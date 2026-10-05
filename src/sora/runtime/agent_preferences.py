"""Canonical specialist preferences, not a second provider configuration store."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, StrictBool, model_validator

from sora.contracts.base import StrictModel
from sora.contracts.models import ModelId, ReasoningEffort, WorkspaceMode


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

class AgentPreferences(StrictModel):
    codex: AgentPreference = Field(default_factory=lambda: AgentPreference(
        purpose="Coding, repository changes, tests and specialist reasoning through Codex.",
    ))
    hermes: AgentPreference = Field(default_factory=lambda: AgentPreference(
        purpose="General specialist tasks using Hermes' own native tools and integrations.",
    ))
    antigravity: AgentPreference = Field(default_factory=lambda: AgentPreference(
        purpose="Research, planning and project work through Antigravity's native tools.",
    ))

    @model_validator(mode="after")
    def harness_efforts(self) -> AgentPreferences:
        if self.hermes.preferred_effort != "configured":
            raise ValueError("Hermes does not expose per-run reasoning effort")
        effort = self.antigravity.preferred_effort
        if effort not in {"configured", "low", "medium", "high", "max"}:
            raise ValueError("Antigravity effort must be configured, low, medium, high or max")
        tier = self.antigravity.preferred_model.rsplit("-", 1)[-1]
        if tier in {"low", "medium", "high", "max"} and effort not in {"configured", tier}:
            raise ValueError("The Antigravity model already specifies a different effort tier")
        return self

    def for_provider(self, provider: str) -> AgentPreference | None:
        name = {"codex-app-server": "codex", "hermes-acp": "hermes"}.get(provider, provider)
        return getattr(self, name, None) if name in {"codex", "hermes", "antigravity"} else None

    def enabled_state(self) -> tuple[bool, bool, bool]:
        return self.codex.enabled, self.hermes.enabled, self.antigravity.enabled
