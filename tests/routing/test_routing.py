from __future__ import annotations

from datetime import UTC, datetime
from typing import NamedTuple

import pytest

from sora.contracts.models import ProviderErrorCode, TaskRecord, TaskStatus
from sora.providers.base import ProviderLaunchError
from sora.routing.router import (
    RoutingEngine,
    TaskIntentCategory,
)


class SimpleTask(NamedTuple):
    task_id: str
    status: TaskStatus
    effective_backend: str | None = None
    requested_backend: str = "auto"


def test_dialogue_fast_path_routing() -> None:
    engine = RoutingEngine()
    decision = engine.route("Hello SORA, how are you today?")
    assert decision.category is TaskIntentCategory.DIALOGUE_FAST_PATH
    assert decision.selected_provider == "deterministic"
    assert decision.rule_name == "dialogue_fast_path"
    assert decision.fallback_providers == ()


def test_status_lookup_fast_path_routing() -> None:
    engine = RoutingEngine()
    decision = engine.route("What are you doing right now?")
    assert decision.category is TaskIntentCategory.STATUS_LOOKUP
    assert decision.selected_provider == "deterministic"
    assert decision.rule_name == "status_lookup_fast_path"
    assert decision.fallback_providers == ()


def test_research_deep_reasoning_routing() -> None:
    engine = RoutingEngine(
        registered_providers=["antigravity", "hermes", "deterministic"],
    )
    decision = engine.route("Research the performance implications of SQLite WAL mode.")
    assert decision.category is TaskIntentCategory.RESEARCH
    assert decision.selected_provider == "antigravity"
    assert decision.rule_name == "deep_reasoning_rule"
    assert "hermes" in decision.fallback_providers
    assert "deterministic" in decision.fallback_providers


def test_coding_read_routing() -> None:
    engine = RoutingEngine(
        registered_providers=["codex", "antigravity", "deterministic"],
    )
    decision = engine.route("Read file src/sora/runtime/service.py and inspect code.")
    assert decision.category is TaskIntentCategory.CODING_READ
    assert decision.selected_provider == "codex"
    assert decision.rule_name == "coding_read_rule"
    assert "antigravity" in decision.fallback_providers


def test_coding_write_held_pending_p05_3() -> None:
    engine = RoutingEngine(
        registered_providers=["antigravity", "codex", "deterministic"],
        has_worktree_isolation=False,
    )
    decision = engine.route("Write code to implement feature X and edit file.")
    assert decision.category is TaskIntentCategory.CODING_WRITE
    assert decision.rule_name == "coding_write_rule"
    assert decision.metadata.get("p05_deferred") is True
    assert "Active coding writes deferred" in str(decision.metadata.get("warning"))


def test_coding_write_routes_only_to_codex_when_isolation_is_available() -> None:
    engine = RoutingEngine(
        registered_providers=["antigravity", "codex", "hermes", "deterministic"],
        has_worktree_isolation=True,
    )
    decision = engine.route("Write code to implement feature X and edit file.")
    assert decision.category is TaskIntentCategory.CODING_WRITE
    assert decision.selected_provider == "codex"
    assert decision.fallback_providers == ()
    assert "p05_deferred" not in decision.metadata


def test_explicit_coding_write_is_deferred_without_owned_workspace() -> None:
    engine = RoutingEngine(
        registered_providers=["codex"],
        has_worktree_isolation=False,
    )
    decision = engine.route(
        "Implement feature X and edit file.",
        explicit_provider="codex",
    )
    assert decision.selected_provider == "codex"
    assert decision.metadata.get("p05_deferred") is True


def test_deterministic_offline_rule() -> None:
    engine = RoutingEngine()
    decision = engine.route("Run offline deterministic synthetic check.")
    assert decision.category is TaskIntentCategory.DETERMINISTIC_OFFLINE
    assert decision.selected_provider == "deterministic"
    assert decision.rule_name == "deterministic_offline_rule"


def test_manual_override_preserves_explicit_backend() -> None:
    engine = RoutingEngine(registered_providers=["antigravity", "hermes", "deterministic"])
    decision = engine.route(
        "Research the codebase",
        explicit_provider="hermes",
    )
    assert decision.selected_provider == "hermes"
    assert decision.rule_name == "manual_override"
    assert decision.fallback_providers == ()


def test_manual_override_rejects_missing_backend_without_silent_substitution() -> None:
    engine = RoutingEngine(registered_providers=["deterministic", "antigravity"])
    with pytest.raises(ProviderLaunchError) as exc_info:
        engine.route("Do something", explicit_provider="nonexistent-backend")
    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE
    assert "silent substitution prohibited" in str(exc_info.value)


def test_privacy_scope_containment_disallows_cloud_providers() -> None:
    engine = RoutingEngine(
        registered_providers=["codex", "antigravity", "deterministic"],
        cloud_providers={"codex"},
        local_providers={"antigravity", "deterministic"},
    )
    # In local-only context, cloud providers cannot be auto-selected
    decision = engine.route(
        "Read file and inspect code",
        is_local_only=True,
    )
    assert decision.selected_provider != "codex"
    assert decision.selected_provider == "antigravity"
    assert "codex" not in decision.fallback_providers


def test_privacy_scope_containment_rejects_explicit_cloud_override() -> None:
    engine = RoutingEngine(
        registered_providers=["codex", "antigravity", "deterministic"],
        cloud_providers={"codex"},
    )
    with pytest.raises(ProviderLaunchError) as exc_info:
        engine.route(
            "Inspect code",
            explicit_provider="codex",
            context_scope="owner-local/private",
        )
    assert exc_info.value.code is ProviderErrorCode.UNAVAILABLE
    assert "violates local-only privacy scope" in str(exc_info.value)


def test_conversational_steering_disambiguation() -> None:
    engine = RoutingEngine()
    now = datetime.now(UTC)

    task_cody = TaskRecord(
        task_id="task-cody-1",
        owner_id="owner-local",
        creator_message_id="msg-1",
        status=TaskStatus.REASONING,
        requested_backend="codex",
        effective_backend="codex",
        base_revision=1,
        created_at=now,
        updated_at=now,
    )
    task_hermes = TaskRecord(
        task_id="task-hermes-1",
        owner_id="owner-local",
        creator_message_id="msg-2",
        status=TaskStatus.WORKING,
        requested_backend="hermes",
        effective_backend="hermes",
        base_revision=1,
        created_at=now,
        updated_at=now,
    )

    # Specific specialist names resolve deterministically
    assert (
        engine.disambiguate_steering("Tell Cody not to modify public API", [task_cody, task_hermes])
        == "task-cody-1"
    )
    assert (
        engine.disambiguate_steering("Tell Hermes to focus on docs", [task_cody, task_hermes])
        == "task-hermes-1"
    )

    # Ambiguous pronoun with multiple tasks returns None to avoid affecting arbitrary work
    assert (
        engine.disambiguate_steering("Tell him to stop", [task_cody, task_hermes])
        is None
    )

    # Unambiguous pronoun with exactly 1 active task resolves to that task
    assert (
        engine.disambiguate_steering("Tell him to stop", [task_cody])
        == "task-cody-1"
    )

    # No active tasks returns None
    assert engine.disambiguate_steering("Tell him to stop", []) is None
