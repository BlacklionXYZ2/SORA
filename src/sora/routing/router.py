"""Deterministic rule-based routing engine for reasoning providers."""

from __future__ import annotations

import re
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import Field, JsonValue

from sora.contracts.base import Identifier, NonEmptyText, StrictModel
from sora.contracts.models import ProviderErrorCode, TaskRecord, TaskStatus
from sora.providers.base import ProviderLaunchError


class TaskIntentCategory(StrEnum):
    DIALOGUE_FAST_PATH = "dialogue_fast_path"
    STATUS_LOOKUP = "status_lookup"
    RESEARCH = "research"
    CODING_READ = "coding_read"
    CODING_WRITE = "coding_write"
    REASONING_GENERAL = "reasoning_general"
    DETERMINISTIC_OFFLINE = "deterministic_offline"


class RoutingDecision(StrictModel):
    selected_provider: Identifier
    rule_name: Identifier
    reason: NonEmptyText
    category: TaskIntentCategory
    fallback_providers: tuple[Identifier, ...] = ()
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


# Regex patterns for fast-path and intent classification
_DIALOGUE_PATTERNS = re.compile(
    r"^\s*(?:hi|hello|hey|good morning|good afternoon|good evening|"
    r"thanks|thank you|how are you|who are you)\b",
    re.IGNORECASE,
)
_STATUS_PATTERNS = re.compile(
    r"\b(?:what are you doing|status of tasks?|list tasks?|check tasks?|what's running)\b",
    re.IGNORECASE,
)
_CODING_WRITE_PATTERNS = re.compile(
    r"\b(?:write code|refactor|fix the bug|patch|edit(?:ing)?|create file|"
    r"implement feature|modify code|change (?:the )?(?:code|file))\b",
    re.IGNORECASE,
)
_CODING_READ_PATTERNS = re.compile(
    r"\b(?:read file|inspect code|review diff|check syntax|explain code|"
    r"find usage|codebase|repository)\b",
    re.IGNORECASE,
)
_RESEARCH_PATTERNS = re.compile(
    r"\b(?:research|investigate|why does|compare|deep dive|literature|explore|search the web)\b",
    re.IGNORECASE,
)
_OFFLINE_PATTERNS = re.compile(
    r"\b(?:offline|deterministic|mock test|synthetic)\b",
    re.IGNORECASE,
)

# Regex patterns for steering disambiguation
_HERMES_TARGET = re.compile(r"\bhermes\b", re.IGNORECASE)
_CODY_TARGET = re.compile(r"\b(?:cody|codex)\b", re.IGNORECASE)
_ANTIGRAVITY_TARGET = re.compile(r"\b(?:antigravity|ag)\b", re.IGNORECASE)
_PRONOUN_TARGET = re.compile(r"\b(?:him|her|them|it)\b", re.IGNORECASE)


class RoutingEngine:
    """Deterministic routing engine matching tasks to specialized providers."""

    def __init__(
        self,
        *,
        default_provider: str = "deterministic",
        registered_providers: Sequence[str] | set[str] | None = None,
        cloud_providers: set[str] | None = None,
        local_providers: set[str] | None = None,
        has_worktree_isolation: bool = False,
    ) -> None:
        self.default_provider = default_provider
        self.registered_providers = (
            set(registered_providers)
            if registered_providers is not None
            else {"deterministic", "hermes", "codex", "antigravity"}
        )
        self.cloud_providers = (
            set(cloud_providers) if cloud_providers is not None else {"codex"}
        )
        self.local_providers = (
            set(local_providers)
            if local_providers is not None
            else {"deterministic", "hermes", "antigravity"}
        )
        self.has_worktree_isolation = has_worktree_isolation

    def classify_intent(self, intent: str) -> TaskIntentCategory:
        """Classify user intent deterministically without external calls."""
        stripped = intent.strip()
        if _DIALOGUE_PATTERNS.search(stripped):
            return TaskIntentCategory.DIALOGUE_FAST_PATH
        if _STATUS_PATTERNS.search(stripped):
            return TaskIntentCategory.STATUS_LOOKUP
        if _OFFLINE_PATTERNS.search(stripped):
            return TaskIntentCategory.DETERMINISTIC_OFFLINE
        if _CODING_WRITE_PATTERNS.search(stripped):
            return TaskIntentCategory.CODING_WRITE
        if _CODING_READ_PATTERNS.search(stripped):
            return TaskIntentCategory.CODING_READ
        if _RESEARCH_PATTERNS.search(stripped):
            return TaskIntentCategory.RESEARCH
        return TaskIntentCategory.REASONING_GENERAL

    def route(
        self,
        intent: str,
        *,
        explicit_provider: str | None = None,
        context_scope: str | None = None,
        is_local_only: bool = False,
    ) -> RoutingDecision:
        """Route a task to the appropriate reasoning provider.
        
        Enforces:
        - Manual overrides: explicit requests are honored without silent substitution.
        - Privacy scope containment: local-only context never routes or falls back to cloud.
        - Dialogue fast-paths: conversational and status queries bypass heavy models.
        - P05.3 safety boundary: coding writes without worktree isolation are held.
        - Bounded fallbacks: auto-routing generates an ordered fallback list.
        """
        category = self.classify_intent(intent)
        effective_local_only = is_local_only or (
            context_scope is not None
            and any(marker in context_scope.lower() for marker in ("local", "private"))
        )

        # 1. Manual override
        if explicit_provider is not None and explicit_provider != "auto":
            if explicit_provider not in self.registered_providers:
                raise ProviderLaunchError(
                    ProviderErrorCode.UNAVAILABLE,
                    f"Requested provider '{explicit_provider}' is not available "
                    "(silent substitution prohibited)",
                )
            if effective_local_only and explicit_provider in self.cloud_providers:
                raise ProviderLaunchError(
                    ProviderErrorCode.UNAVAILABLE,
                    f"Requested cloud provider '{explicit_provider}' violates "
                    "local-only privacy scope",
                )
            manual_metadata: dict[str, JsonValue] = {}
            if category is TaskIntentCategory.CODING_WRITE and not self.has_worktree_isolation:
                manual_metadata["p05_deferred"] = True
                manual_metadata["warning"] = "Coding writes require an owned P05 workspace"
            return RoutingDecision(
                selected_provider=explicit_provider,
                rule_name="manual_override",
                reason=f"Explicit override requested backend: {explicit_provider}",
                category=category,
                fallback_providers=(),
                metadata=manual_metadata,
            )

        # Candidates filtered by privacy scope
        candidates = {
            p
            for p in self.registered_providers
            if not effective_local_only or p not in self.cloud_providers
        }
        if not candidates:
            raise ProviderLaunchError(
                ProviderErrorCode.UNAVAILABLE,
                "No provider satisfies the requested privacy scope",
            )

        # 2. Dialogue / Status fast-paths
        if category is TaskIntentCategory.DIALOGUE_FAST_PATH:
            return RoutingDecision(
                selected_provider="deterministic",
                rule_name="dialogue_fast_path",
                reason="Conversational greeting/banter handled on fast-path dialogue",
                category=category,
                fallback_providers=(),
            )

        if category is TaskIntentCategory.STATUS_LOOKUP:
            return RoutingDecision(
                selected_provider="deterministic",
                rule_name="status_lookup_fast_path",
                reason="Status check handled on fast-path runtime state",
                category=category,
                fallback_providers=(),
            )

        # 3. Deterministic offline
        if category is TaskIntentCategory.DETERMINISTIC_OFFLINE:
            return RoutingDecision(
                selected_provider="deterministic",
                rule_name="deterministic_offline_rule",
                reason="Explicitly requested deterministic/offline execution",
                category=category,
                fallback_providers=(),
            )

        # 4. Coding write
        if category is TaskIntentCategory.CODING_WRITE:
            metadata: dict[str, JsonValue] = {}
            if not self.has_worktree_isolation:
                metadata["p05_deferred"] = True
                metadata["warning"] = "Active coding writes deferred pending P05.3 isolation"

            # Only Codex currently binds write authority to a manager-owned worktree.
            # Without that boundary, another harness may plan but must not mutate.
            selected = (
                "codex"
                if self.has_worktree_isolation and "codex" in candidates
                else (
                    "antigravity"
                    if "antigravity" in candidates
                    else ("codex" if "codex" in candidates else "deterministic")
                )
            )
            fallbacks = () if self.has_worktree_isolation else tuple(
                p
                for p in ("antigravity", "hermes", "deterministic")
                if p in candidates and p != selected
            )
            return RoutingDecision(
                selected_provider=selected,
                rule_name="coding_write_rule",
                reason=(
                    "Coding write task routed for planning/analysis; "
                    "in-place file mutations held pending P05.3"
                    if not self.has_worktree_isolation
                    else "Coding write task routed to Codex in an owned worktree"
                ),
                category=category,
                fallback_providers=fallbacks,
                metadata=metadata,
            )

        # 5. Coding read / review
        if category is TaskIntentCategory.CODING_READ:
            selected = "codex" if "codex" in candidates else (
                "antigravity" if "antigravity" in candidates else "deterministic"
            )
            fallbacks = tuple(
                p
                for p in ("antigravity", "hermes", "deterministic")
                if p in candidates and p != selected
            )
            return RoutingDecision(
                selected_provider=selected,
                rule_name="coding_read_rule",
                reason="Code inspection/review routed to coding specialist",
                category=category,
                fallback_providers=fallbacks,
            )

        # 6. Research / Deep reasoning / General
        selected = "antigravity" if "antigravity" in candidates else (
            "hermes" if "hermes" in candidates else "deterministic"
        )
        fallbacks = tuple(
            p
            for p in ("hermes", "antigravity", "deterministic")
            if p in candidates and p != selected
        )
        return RoutingDecision(
            selected_provider=selected,
            rule_name="deep_reasoning_rule",
            reason="Research and reasoning task routed to reasoning specialist",
            category=category,
            fallback_providers=fallbacks,
        )

    def disambiguate_steering(
        self,
        instruction: str,
        active_tasks: Sequence[TaskRecord | Any],
    ) -> str | None:
        """Resolve conversational steering instruction to a target task_id.
        
        Matches specialist aliases (Cody -> codex, Hermes -> hermes, AG -> antigravity)
        or pronouns ("him", "her", "them") if exactly one candidate is running.
        Returns None for ambiguous references to prevent affecting arbitrary work.
        """
        # Filter active tasks only
        running = [
            t
            for t in active_tasks
            if getattr(t, "status", None)
            in {
                TaskStatus.QUEUED,
                TaskStatus.ROUTING,
                TaskStatus.REASONING,
                TaskStatus.WORKING,
            }
        ]
        if not running:
            return None

        # 1. Direct name references
        if _CODY_TARGET.search(instruction):
            matches = [
                t
                for t in running
                if getattr(t, "effective_backend", None) == "codex"
                or getattr(t, "requested_backend", None) == "codex"
            ]
            return matches[0].task_id if len(matches) == 1 else None

        if _HERMES_TARGET.search(instruction):
            matches = [
                t
                for t in running
                if getattr(t, "effective_backend", None) == "hermes"
                or getattr(t, "requested_backend", None) == "hermes"
            ]
            return matches[0].task_id if len(matches) == 1 else None

        if _ANTIGRAVITY_TARGET.search(instruction):
            matches = [
                t
                for t in running
                if getattr(t, "effective_backend", None) == "antigravity"
                or getattr(t, "requested_backend", None) == "antigravity"
            ]
            return matches[0].task_id if len(matches) == 1 else None

        # 2. Pronoun reference: only safe if exactly one active task exists
        if _PRONOUN_TARGET.search(instruction):
            if len(running) == 1:
                return running[0].task_id
            # More than one active task: ambiguous! Do not affect arbitrary work.
            return None

        # No target recognized
        return None
