"""Dynamic capability resolution with scope containment and bounded selection."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sora.contracts.base import require_aware
from sora.contracts.models import (
    ActiveCapabilityManifestEntry,
    ActiveCapabilitySet,
    CapabilityCategory,
    CapabilityDescriptor,
    CapabilityIndex,
    CapabilityIndexEntry,
    CapabilityResolutionRequest,
    CapabilityScope,
)

_SCOPE_HIERARCHY: dict[CapabilityScope, set[CapabilityScope]] = {
    CapabilityScope.LOCAL_OWNER: {
        CapabilityScope.LOCAL_OWNER,
        CapabilityScope.LOCAL_RESTRICTED,
        CapabilityScope.NETWORK_PUBLIC,
    },
    CapabilityScope.LOCAL_RESTRICTED: {
        CapabilityScope.LOCAL_RESTRICTED,
        CapabilityScope.NETWORK_PUBLIC,
    },
    CapabilityScope.NETWORK_PUBLIC: {
        CapabilityScope.NETWORK_PUBLIC,
    },
    CapabilityScope.REMOTE_GUEST: set(),  # strictly unavailable
}

_CATEGORY_KEYWORDS: dict[CapabilityCategory, tuple[str, ...]] = {
    CapabilityCategory.MEDIA: ("play", "pause", "track", "song", "volume", "music", "spotify"),
    CapabilityCategory.TASKS: (
        "task", "board", "todo", "doing", "done", "kanban", "cody", "assign"
    ),
    CapabilityCategory.FILES: ("file", "read", "write", "open", "code", "repo", "source"),

    CapabilityCategory.DESKTOP: ("window", "screen", "click", "point", "touch", "look", "button"),
    CapabilityCategory.SOCIAL: ("post", "reply", "social", "nekoverse", "feed", "message"),
    CapabilityCategory.CALENDAR: ("calendar", "meeting", "schedule", "event", "time"),
    CapabilityCategory.DESKTOP_OBJECTS: ("board", "sticky", "widget", "object", "note"),
    CapabilityCategory.REASONING_AGENTS: ("cody", "hermes", "antigravity", "codex", "delegate"),
}


class CapabilityRegistry:
    """Stores all installed capabilities across categories and integrations."""

    def __init__(self) -> None:
        self._capabilities: dict[str, CapabilityDescriptor] = {}

    def register(self, descriptor: CapabilityDescriptor) -> None:
        self._capabilities[descriptor.capability_id] = descriptor

    def get(self, capability_id: str) -> CapabilityDescriptor | None:
        return self._capabilities.get(capability_id)

    def list_all(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(self._capabilities.values())

    def build_index(self, scope: CapabilityScope = CapabilityScope.LOCAL_OWNER) -> CapabilityIndex:
        allowed_scopes = _SCOPE_HIERARCHY.get(scope, set())
        grouped: dict[CapabilityCategory, list[str]] = {}
        for cap in self._capabilities.values():
            if cap.required_scope in allowed_scopes:
                grouped.setdefault(cap.category, []).append(cap.capability_id)

        entries = [
            CapabilityIndexEntry(
                category=category,
                capability_ids=tuple(sorted(ids)),
                summary=f"{category.value} capabilities ({len(ids)} available)",
            )
            for category, ids in sorted(grouped.items(), key=lambda item: item[0].value)
        ]
        return CapabilityIndex(entries=tuple(entries))


class CapabilityResolver:
    """Resolves active capabilities according to relevance, scope, and budget."""

    def __init__(self, revision: int = 1) -> None:
        self.revision = revision

    def resolve(
        self,
        request: CapabilityResolutionRequest,
        registry: CapabilityRegistry,
        *,
        now: datetime | None = None,
        ttl_seconds: float = 300.0,
    ) -> ActiveCapabilitySet:
        resolved_now = now or datetime.now(UTC)
        require_aware(resolved_now, "now")

        manifest: list[ActiveCapabilityManifestEntry] = []
        if request.scope is CapabilityScope.REMOTE_GUEST:
            # Remote guest sessions are structurally disabled by default.
            for cap in registry.list_all():
                manifest.append(
                    ActiveCapabilityManifestEntry(
                        capability_id=cap.capability_id,
                        included=False,
                        reason="remote_guest_unavailable",
                    )
                )
            return ActiveCapabilitySet(
                set_id=f"active-set-{request.request_id}",
                resolver_revision=self.revision,
                scope=request.scope,
                selected_capabilities=(),
                manifest=tuple(manifest),
                expires_at=resolved_now + timedelta(seconds=ttl_seconds),
            )

        allowed_scopes = _SCOPE_HIERARCHY.get(request.scope, set())
        words = set(re.findall(r"\w+", request.intent.lower()))
        active_window_lower = (request.active_window or "").lower()

        scored_candidates: list[tuple[int, CapabilityDescriptor]] = []

        for cap in sorted(registry.list_all(), key=lambda c: c.capability_id):
            # 1. Scope check
            if cap.required_scope not in allowed_scopes:
                manifest.append(
                    ActiveCapabilityManifestEntry(
                        capability_id=cap.capability_id,
                        included=False,
                        reason="privacy_scope_excluded",
                    )
                )
                continue

            # 2. Relevance scoring
            score = 0
            category_keywords = _CATEGORY_KEYWORDS.get(cap.category, ())
            for kw in category_keywords:
                if kw in words or (active_window_lower and kw in active_window_lower):
                    score += 2

            # Verb match
            for verb in cap.verbs:
                if verb.value in words:
                    score += 3

            # Contextual associations
            if request.attention_target_refs and cap.category in {
                CapabilityCategory.DESKTOP,
                CapabilityCategory.FILES,
                CapabilityCategory.TASKS,
            }:
                score += 1

            if request.desktop_object_refs and cap.category in {
                CapabilityCategory.DESKTOP_OBJECTS,
                CapabilityCategory.TASKS,
            }:
                score += 2

            if score == 0:
                manifest.append(
                    ActiveCapabilityManifestEntry(
                        capability_id=cap.capability_id,
                        included=False,
                        reason="not_relevant",
                    )
                )
            else:
                scored_candidates.append((score, cap))

        # Sort descending by score, ascending by capability_id for determinism
        scored_candidates.sort(key=lambda item: (-item[0], item[1].capability_id))

        selected: list[CapabilityDescriptor] = []
        for index, (_, cap) in enumerate(scored_candidates):
            if index < request.max_capabilities:
                selected.append(cap)
                manifest.append(
                    ActiveCapabilityManifestEntry(
                        capability_id=cap.capability_id,
                        included=True,
                        reason="selected",
                    )
                )
            else:
                manifest.append(
                    ActiveCapabilityManifestEntry(
                        capability_id=cap.capability_id,
                        included=False,
                        reason="budget_excluded",
                    )
                )

        return ActiveCapabilitySet(
            set_id=f"active-set-{request.request_id}",
            resolver_revision=self.revision,
            scope=request.scope,
            selected_capabilities=tuple(selected),
            manifest=tuple(manifest),
            expires_at=resolved_now + timedelta(seconds=ttl_seconds),
        )
