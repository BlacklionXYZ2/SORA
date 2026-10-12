"""SORA's own thoughts are ordinary memories, authored by her, dated, and labelled on recall."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sora.contracts.companion_call import CompanionCall
from sora.persistence.records import MemoryState, StoredMemory
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.self_memory import OWN_THOUGHT, memory_label
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope

ROOT = Path(__file__).resolve().parents[2]


class Thinker(DeterministicDialogueProvider):
    """Keeps one thought on the first turn, then just talks; records what it was shown."""

    def __init__(self) -> None:
        self.contexts: list[str] = []
        self.offered: list[frozenset[str]] = []
        self.thought_once = False

    async def choose_call(
        self, prompt: str, observations: str, operations: frozenset[str],
    ) -> CompanionCall:
        self.offered.append(operations)
        if "remember_thought" in operations and not self.thought_once:
            self.thought_once = True
            return CompanionCall.model_validate(
                {"op": "remember_thought", "thought": "I enjoyed planning the trip with him."})
        return CompanionCall.model_validate({"op": "finish"})

    async def respond(self, text: str, context: str, *, active_capabilities: Any = None) -> str:
        self.contexts.append(context)
        return "Sounds lovely."


@pytest.mark.asyncio
async def test_a_kept_thought_is_an_ordinary_memory_authored_by_her(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(SettingsEdit(version=10, expected_revision=0, changes={
        "perception.desktop_context": False, "perception.window_context": False,
        "perception.mode": "native-only"}))
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    thinker = Thinker()
    settings.provider = thinker
    runtime.dialogue_provider = thinker
    try:
        with owner_local_scope():
            await runtime.dialogue("We booked the Lake District cottage!")
        assert "remember_thought" in thinker.offered[0]
        memories = await runtime.repository.list_memories(
            runtime.config.owner_id, project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC))
        own = [m for m in memories if m.provenance.startswith(OWN_THOUGHT)]
        assert [m.content for m in own] == ["I enjoyed planning the trip with him."]
        assert own[0].created_at is not None and own[0].evidence_refs  # dated, with its capture
        # Same table, same scope as the owner's memories: not a separate category.
        assert own[0].scope == "dialogue" and own[0].retention == "durable"
        with owner_local_scope():
            await runtime.dialogue("What did you think of the trip planning?")
        assert "My own earlier thought (" in thinker.contexts[-1]
        assert "I enjoyed planning the trip with him." in thinker.contexts[-1]
    finally:
        await runtime.close()


def test_labels_say_whose_memory_it_is_and_when() -> None:
    def stored(provenance: str, created: datetime | None) -> StoredMemory:
        return StoredMemory(memory_id="memory-1", owner_id="owner-local", content="x",
                            scope="dialogue", sensitivity="private", retention="durable",
                            provenance=provenance, entity_version=1, state=MemoryState.ACTIVE,
                            created_at=created)

    when = datetime(2026, 9, 29, 11, 8, tzinfo=UTC)
    assert memory_label(stored("owner-stated (direct dialogue)", when)) == (
        "Owner-stated memory (29 Sep 2026)")
    assert memory_label(stored(f"{OWN_THOUGHT} (direct dialogue)", when)).startswith(
        "My own earlier thought (29 Sep 2026), an opinion")
    assert memory_label(stored("owner-stated", None)) == "Owner-stated memory (date unknown)"
