from __future__ import annotations

from typing import NamedTuple

import pytest

from sora.contracts.models import TaskStatus
from sora.routing.agent_names import DEFAULT_DIRECTORY, AgentDirectory, AgentName, parse_aliases
from sora.routing.router import RoutingEngine


class SimpleTask(NamedTuple):
    task_id: str
    status: TaskStatus
    effective_backend: str | None = None
    requested_backend: str = "auto"


def test_builtin_colleagues_use_their_vision_names() -> None:
    assert DEFAULT_DIRECTORY.name_for("codex") == "Cody"
    assert DEFAULT_DIRECTORY.name_for("codex-app-server") == "Cody"
    assert DEFAULT_DIRECTORY.name_for("hermes-acp") == "Hermes"
    assert DEFAULT_DIRECTORY.name_for("antigravity") == "Aggie"
    assert DEFAULT_DIRECTORY.name_for("claude-code") == "Claude"
    assert DEFAULT_DIRECTORY.name_for("deterministic") is None


@pytest.mark.parametrize(("text", "key"), [
    ("Ask Cody to look at the tests", "codex"),
    ("ask codey about the build", "codex"),
    ("have Kodi check it", "codex"),
    ("get aggie on it", "antigravity"),
    ("hand it to anti-gravity", "antigravity"),
    ("Aggy, what do you think?", "antigravity"),
    ("let Hermes handle email", "hermes"),
    ("tell Claude to review this", "claude"),
    ("ask clawed to review this", "claude"),
])
def test_spoken_variants_resolve_to_one_agent(text: str, key: str) -> None:
    assert DEFAULT_DIRECTORY.mentioned(text) == (key,)


@pytest.mark.parametrize("text", [
    "the cloud is down",          # "cloud" is ordinary speech, not Claude
    "write some code",            # "code" is not Cody
    "my agenda is full",          # "ag" only as a whole word
    "Codexes are old books",
])
def test_ordinary_words_do_not_name_an_agent(text: str) -> None:
    assert DEFAULT_DIRECTORY.mentioned(text) == ()


def test_requested_needs_a_request_verb() -> None:
    assert DEFAULT_DIRECTORY.requested("Ask Cody to fix the parser") == ("codex",)
    assert DEFAULT_DIRECTORY.requested("send this to Aggie please") == ("antigravity",)
    assert DEFAULT_DIRECTORY.requested("delegate it to Claude") == ("claude",)
    # A mention without a request is not an explicit harness choice.
    assert DEFAULT_DIRECTORY.requested("Cody fixed it yesterday") == ()


def test_custom_nicknames_join_the_directory_and_clashes_are_rejected() -> None:
    names = DEFAULT_DIRECTORY.with_custom([("custom-1", "Pip", parse_aliases("pipp, pippa"))])
    assert names.mentioned("ask pippa to summarise this") == ("custom-1",)
    assert names.requested("ask Pip to summarise this") == ("custom-1",)
    assert names.name_for("custom-1") == "Pip"
    with pytest.raises(ValueError, match="already names another agent"):
        DEFAULT_DIRECTORY.with_custom([("custom-1", "Cody", ())])
    with pytest.raises(ValueError, match="Spoken alias"):
        parse_aliases("ok, <script>")


def test_directory_rejects_duplicate_aliases_between_agents() -> None:
    with pytest.raises(ValueError):
        AgentDirectory([*DEFAULT_DIRECTORY.agents, AgentName("other", "Other", (), ("kody",))])


def test_steering_by_spoken_name_matches_routed_provider_ids() -> None:
    engine = RoutingEngine()
    # Auto-routed tasks record the adapter's provider ID, not the routing key.
    cody = SimpleTask("task-cody", TaskStatus.WORKING, "codex-app-server")
    aggie = SimpleTask("task-aggie", TaskStatus.WORKING, "antigravity")
    claude = SimpleTask("task-claude", TaskStatus.WORKING, "claude-code", "claude")
    tasks = [cody, aggie, claude]
    assert engine.disambiguate_steering("tell codey to stop", tasks) == "task-cody"
    assert engine.disambiguate_steering("cancel Aggie's task", tasks) == "task-aggie"
    assert engine.disambiguate_steering("Claude, focus on the tests", tasks) == "task-claude"
    assert engine.disambiguate_steering("tell Cody and Aggie to stop", tasks) is None


def test_steering_uses_custom_nicknames() -> None:
    names = DEFAULT_DIRECTORY.with_custom([("custom-2", "Juniper", ("june",))])
    engine = RoutingEngine(agent_names=names)
    task = SimpleTask("task-june", TaskStatus.WORKING, "custom-2", "custom-2")
    assert engine.disambiguate_steering("June, stop that", [task]) == "task-june"
