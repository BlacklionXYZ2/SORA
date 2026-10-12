"""Reflection: progress from memories, her own goals, refusals for invented references."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sora.contracts.companion_call import CompanionCall
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.reflection import OPERATIONS
from sora.runtime.self_memory import OWN_THOUGHT
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope

ROOT = Path(__file__).resolve().parents[2]


class Reflector(DeterministicDialogueProvider):
    def __init__(self, script: list[dict[str, Any]]) -> None:
        self.script = script
        self.seen: list[list[dict[str, Any]]] = []
        self.offered: list[frozenset[str]] = []

    async def choose_call(
        self, prompt: str, observations: str, operations: frozenset[str],
    ) -> CompanionCall:
        self.seen.append(json.loads(observations.split("\n", 1)[1]))
        self.offered.append(operations)
        step = self.script.pop(0) if self.script else {"op": "finish"}
        return CompanionCall.model_validate(step)


async def runtime_with(tmp_path: Path, provider: Any) -> SoraRuntime:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider(), dialogue_provider=provider)
    await runtime.start()
    return runtime


@pytest.mark.asyncio
async def test_reflection_notes_progress_adds_goals_and_refuses_invented_targets(
    tmp_path: Path,
) -> None:
    reflector = Reflector([
        {"op": "note_goal", "target": "g1", "text": "Helped him plan the trip calmly",
         "memories": ["m1"]},
        {"op": "note_goal", "target": "g9", "text": "No such goal", "memories": []},
        {"op": "note_goal", "target": "g1", "text": "Invented memory", "memories": ["m7"]},
        {"op": "add_goal", "text": "Learn what makes him laugh", "why": "I like it when he does"},
        {"op": "remember_thought", "thought": "Reflecting makes me feel more like myself."},
        {"op": "finish"},
    ])
    runtime = await runtime_with(tmp_path, reflector)
    try:
        goals = runtime.goal_store()
        goal = await goals.add("Be a calm presence", "He gets stressed before exams",
                               actor="owner")
        await runtime.repository.add_memory(
            memory_id="memory-trip", owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id, content="We booked the Lake District cottage.",
            scope="dialogue", sensitivity="private", retention="durable",
            provenance="owner-stated (test)")
        with owner_local_scope():
            reflection = await runtime.reflect_now()
        assert reflector.offered[0] == OPERATIONS
        first = {row["operation"]: row["data"] for row in reflector.seen[0]}
        assert first["my_goals"]["goals"][0]["target"] == "g1"
        assert first["memories_since_last_reflection"]["memories"][0]["target"] == "m1"
        statuses = [(a["op"], a["status"]) for a in reflection.actions]
        assert statuses == [("note_goal", "ok"), ("note_goal", "refused"),
                            ("note_goal", "refused"), ("add_goal", "ok"),
                            ("remember_thought", "ok")]
        everything = await goals.goals(include_closed=True)
        noted = next(g for g in everything if g.goal_id == goal.goal_id)
        progress = [e for e in noted.events if e.kind == "progress"]
        assert [(e.text, e.memory_ids, e.actor) for e in progress] == [
            ("Helped him plan the trip calmly", ("memory-trip",), "sora")]
        assert any(g.text == "Learn what makes him laugh" and g.origin == "sora"
                   for g in everything)
        memories = await runtime.repository.list_memories(
            runtime.config.owner_id, project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC))
        assert any(m.provenance.startswith(OWN_THOUGHT) for m in memories)
        assert (tmp_path / "self/goals.md").is_file()
        # The next reflection only sees memories made after this one.
        reflector.script = [{"op": "finish"}]
        with owner_local_scope():
            second = await runtime.reflect_now()
        assert second.memories_seen == 1  # just the thought she kept during the first
    finally:
        await runtime.close()
