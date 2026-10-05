"""Deterministic context selection with explicit scope and exclusion evidence."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sora.contracts.base import Identifier, NonEmptyText, StrictModel, require_aware
from sora.contracts.models import ActiveCapabilitySet
from sora.identity.loader import IdentityBundle


class ContextSource(StrEnum):
    USER_MESSAGE = "USER_MESSAGE"
    SORA_MESSAGE = "SORA_MESSAGE"
    FACT = "FACT"
    MEMORY = "MEMORY"
    INFERENCE = "INFERENCE"
    TASK = "TASK"
    TASK_STATUS = "TASK_STATUS"
    EDITOR_CONTEXT = "EDITOR_CONTEXT"
    REFERENCE_CONTEXT = "REFERENCE_CONTEXT"
    AGENT_RESULT = "AGENT_RESULT"
    TOOL_RESULT = "TOOL_RESULT"
    DESKTOP_STATE = "DESKTOP_STATE"


class ContextItem(StrictModel):
    source_id: Identifier
    source: ContextSource
    owner_id: Identifier
    project_id: Identifier | None = None
    content: NonEmptyText
    sensitivity: str = "normal"
    valid_until: datetime | None = None


class ManifestEntry(StrictModel):
    source_id: Identifier
    source: ContextSource
    included: bool
    reason: str


class ContextManifest(StrictModel):
    compiler_version: str = "1.0"
    owner_id: Identifier
    project_id: Identifier | None
    max_chars: int
    rendered_chars: int
    entries: tuple[ManifestEntry, ...]


class CompiledContext(StrictModel):
    text: str
    manifest: ContextManifest


class ContextBudgetError(ValueError):
    pass


_PRIORITY = {
    ContextSource.FACT: 0,
    ContextSource.TASK_STATUS: 1,
    ContextSource.TASK: 2,
    ContextSource.EDITOR_CONTEXT: 3,
    ContextSource.REFERENCE_CONTEXT: 3,
    ContextSource.USER_MESSAGE: 4,
    ContextSource.SORA_MESSAGE: 5,
    ContextSource.AGENT_RESULT: 6,
    ContextSource.TOOL_RESULT: 7,
    ContextSource.MEMORY: 8,
    ContextSource.DESKTOP_STATE: 9,
    ContextSource.INFERENCE: 10,
}


def compile_context(
    *,
    identity: IdentityBundle,
    owner_id: str,
    project_id: str | None,
    constraints: tuple[str, ...],
    items: tuple[ContextItem, ...],
    observed_at: datetime,
    max_chars: int,
    privacy_scope: str = "local_owner",
    active_capabilities: ActiveCapabilitySet | None = None,
) -> CompiledContext:
    require_aware(observed_at, "observed_at")
    if max_chars < 256:
        raise ValueError("max_chars must be at least 256")

    identity_text = "\n".join(
        f"[IDENTITY:{name}]\n{content}" for name, content in identity.files.items()
    )
    constraint_text = "\n".join(f"[CONSTRAINT]\n{constraint}" for constraint in constraints)
    mandatory_parts = [part for part in (identity_text, constraint_text) if part]

    if active_capabilities and active_capabilities.selected_capabilities:
        cap_lines = [
            f"- {cap.capability_id} ({cap.category.value}): {cap.description}"
            for cap in active_capabilities.selected_capabilities
        ]
        mandatory_parts.append("[ACTIVE_CAPABILITIES]\n" + "\n".join(cap_lines))

    mandatory = "\n\n".join(mandatory_parts)
    if len(mandatory) > max_chars:
        raise ContextBudgetError("identity and exact constraints exceed the context budget")

    entries: list[ManifestEntry] = []
    eligible: list[ContextItem] = []
    for item in items:
        reason: str | None = None
        if privacy_scope == "network_public" and item.sensitivity != "public":
            reason = "privacy_scope_excluded"
        elif item.owner_id != owner_id:
            reason = "owner_scope_mismatch"
        elif item.project_id is not None and item.project_id != project_id:
            reason = "project_scope_mismatch"
        elif item.sensitivity == "secret":
            reason = "secret_excluded"
        elif item.valid_until is not None and observed_at >= item.valid_until:
            reason = "expired"
        if reason:
            entries.append(
                ManifestEntry(
                    source_id=item.source_id,
                    source=item.source,
                    included=False,
                    reason=reason,
                )
            )
        else:
            eligible.append(item)

    rendered = mandatory
    for item in sorted(
        eligible, key=lambda candidate: (_PRIORITY[candidate.source], candidate.source_id)
    ):
        block = f"[{item.source.value}:{item.source_id}]\n{item.content}"
        candidate = f"{rendered}\n\n{block}" if rendered else block
        included = len(candidate) <= max_chars
        entries.append(
            ManifestEntry(
                source_id=item.source_id,
                source=item.source,
                included=included,
                reason="selected" if included else "budget_excluded",
            )
        )
        if included:
            rendered = candidate

    return CompiledContext(
        text=rendered,
        manifest=ContextManifest(
            owner_id=owner_id,
            project_id=project_id,
            max_chars=max_chars,
            rendered_chars=len(rendered),
            entries=tuple(entries),
        ),
    )
