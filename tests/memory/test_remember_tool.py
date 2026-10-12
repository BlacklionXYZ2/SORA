"""The remember tool: her title and description, stored with the whole turn and its media."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import struct
import wave
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from sora.contracts.companion_call import CompanionCall, Remember
from sora.memory.entries import forget_entry, read_entry, write_entry
from sora.memory.layers import LayerSet
from sora.memory.manager import DecisionLog, MemoryManager
from sora.memory.store import MemoryVectorStore
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.providers.turn_audio import turn_audio
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.remember_turn import remember_turn
from sora.runtime.self_memory import memory_label
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.memory.test_memory_manager import LOOSE, FakeEmbedder

ROOT = Path(__file__).resolve().parents[2]
PNG = "data:image/png;base64," + base64.b64encode(
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64).decode()


def wav(seconds: float = 0.5) -> str:
    stream = io.BytesIO()
    with wave.open(stream, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(16000)
        clip.writeframes(struct.pack("<h", 0) * int(16000 * seconds))
    return base64.b64encode(stream.getvalue()).decode()


class Rememberer(DeterministicDialogueProvider):
    """Calls remember on the first turn; must never be asked the old yes/no question."""

    def __init__(self) -> None:
        self.offered: list[frozenset[str]] = []
        self.done = False

    async def choose_call(self, prompt: str, observations: str,
                          operations: frozenset[str]) -> CompanionCall:
        self.offered.append(operations)
        if "remember" in operations and not self.done:
            self.done = True
            return CompanionCall.model_validate({
                "op": "remember", "title": "Favourite colour",
                "description": "His favourite colour is now green, not teal."})
        return CompanionCall.model_validate({"op": "finish"})

    async def respond(self, text: str, context: str, *, active_capabilities: Any = None) -> str:
        return "Green it is!"

    async def choose_memory(self, prompt: str) -> Any:
        raise AssertionError("the remember tool replaces the after-turn yes/no call")


@pytest.mark.asyncio
async def test_the_tool_stores_the_memory_with_the_whole_turn(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(SettingsEdit(version=10, expected_revision=0, changes={
        "perception.desktop_context": False, "perception.window_context": False,
        "perception.mode": "native-only"}))
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    provider = Rememberer()
    settings.provider = provider
    runtime.dialogue_provider = provider
    try:
        with owner_local_scope(), turn_audio(wav()):
            await runtime.dialogue("oh and it's green now, not teal")
        assert "remember" in provider.offered[0]
        memories = await runtime.repository.list_memories(
            runtime.config.owner_id, project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC))
        [memory] = memories
        assert memory.content == "His favourite colour is now green, not teal."
        assert memory.title == "Favourite colour"
        assert memory_label(memory).endswith('"Favourite colour"')
        entry = read_entry(runtime.memory_entries_root(), memory.memory_id)
        assert entry is not None and entry.owner_text == "oh and it's green now, not teal"
        assert entry.reply == "Green it is!" and entry.context["decided_by"] == "remember tool"
        assert [m.file for m in entry.media] == ["voice.wav"]
        assert entry.media[0].seconds == 0.5
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_entries_keep_images_and_voice_and_forgetting_deletes_them(tmp_path: Path) -> None:
    root = tmp_path / "entries"
    entry = write_entry(root, memory_id="memory-1", created_at=datetime.now(UTC),
                        title="Desk", description="He showed me his new desk setup.",
                        owner_text="look at my desk!", images=[(PNG, "owner"), (PNG, "screen"),
                                                               ("data:text/html,x", "screen")],
                        audio_wav_base64=wav(1.0))
    assert [(m.file, m.source) for m in entry.media] == [
        ("image-1.png", "owner"), ("image-2.png", "screen"), ("voice.wav", "voice")]
    assert not list(root.glob(".*partial"))  # written in one step
    assert forget_entry(root, "memory-1") and not (root / "memory-1").exists()
    assert not forget_entry(root, "../outside")


@pytest.mark.asyncio
async def test_the_manager_scores_every_part_of_a_remembered_turn(tmp_path: Path) -> None:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider())
    await runtime.start()
    try:
        stored = await remember_turn(
            runtime.repository, Remember(op="remember", title="Desk setup",
                                         description="His desk has two monitors and a lamp."),
            entries=runtime.memory_entries_root(), owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id, owner_text="my desk has two monitors",
            reply="Two monitors and a lamp, nice desk!", read_observations="Windows open: Spotify",
            images=[(PNG, "screen"), (PNG, "screen")], audio_wav_base64=wav(),
            provider="test", context={})
        assert stored is not None
        memory_id, media = stored
        assert media == 3
        again = await remember_turn(
            runtime.repository, Remember(op="remember", title="Desk",
                                         description="His desk has two monitors and a lamp."),
            entries=runtime.memory_entries_root(), owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id, owner_text="x", reply="", read_observations="",
            images=[], audio_wav_base64=None, provider="test", context={})
        assert again is None  # a repeat in the same words
        manager = MemoryManager(
            repository=runtime.repository, store=MemoryVectorStore(runtime.repository.database),
            embedder=FakeEmbedder(), layers=LayerSet(tmp_path / "layers"),
            log=DecisionLog(tmp_path / "decisions"), owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id, captures_root=tmp_path / "captures",
            thresholds=LOOSE, entries_root=runtime.memory_entries_root())
        assert (await manager.run()).embedded == 1
        entry = read_entry(runtime.memory_entries_root(), memory_id)
        assert entry is not None and entry.status == "processed"
        verdicts = {name: v.kept for name, v in entry.parts.items()}
        assert verdicts["words"] and verdicts["reply"] and verdicts["voice"]
        assert verdicts["image-1"] and not verdicts["image-2"]  # the second is the same picture
        assert not verdicts["read"]  # the window list is unrelated to the desk
        parts = {part for mid, part, _ in await manager.store.vectors(FakeEmbedder.identity)}
        assert {"owner", "words", "reply", "image-1", "voice", "whole"} <= parts
        assert "image-2" not in parts and "read" not in parts
        folder = runtime.memory_entries_root() / memory_id
        assert (folder / "image-1.png").exists() and not (folder / "image-2.png").exists()
        assert [m.file for m in entry.media] == ["image-1.png", "voice.wav"]  # not stored
        logged = [json.loads(line) for f in (tmp_path / "decisions").glob("*.jsonl")
                  for line in f.read_text("utf-8").splitlines()]
        assert {r["part"] for r in logged if r["layer"] == "relevance"} == {
            "reply", "read", "image-1", "image-2", "voice"}
    finally:
        await runtime.close()


class Instructed(Rememberer):
    def __init__(self) -> None:
        super().__init__()
        self.contexts: list[str] = []

    async def choose_call(self, prompt: str, observations: str,
                          operations: frozenset[str]) -> CompanionCall:
        if "remember" in operations and not self.done:
            self.done = True
            return CompanionCall.model_validate({
                "op": "remember", "title": "Answer length", "standing": True,
                "description": "He wants short answers from now on."})
        return CompanionCall.model_validate({"op": "finish"})

    async def respond(self, text: str, context: str, *, active_capabilities: Any = None) -> str:
        self.contexts.append(context)
        return "Okay."


@pytest.mark.asyncio
async def test_a_standing_instruction_stays_in_view_on_every_turn(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(SettingsEdit(version=10, expected_revision=0, changes={
        "perception.desktop_context": False, "perception.window_context": False,
        "perception.mode": "native-only"}))
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    provider = Instructed()
    settings.provider = provider
    runtime.dialogue_provider = provider
    try:
        with owner_local_scope():
            await runtime.dialogue("From now on keep your answers short.")
            await runtime.dialogue("Tell me about the solar system.")
        [memory] = await runtime.repository.list_memories(
            runtime.config.owner_id, project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC))
        assert memory.scope == "standing"
        assert "How the owner has asked me to behave from now on" in provider.contexts[-1]
        assert "He wants short answers from now on." in provider.contexts[-1]
        assert provider.contexts[-1].rstrip().endswith(
            "[HOW THE OWNER ASKED ME TO BEHAVE: follow these in this reply] "
            "(1) He wants short answers from now on.")
    finally:
        await runtime.close()


@pytest.mark.parametrize(("words", "standing"), [
    ("From now on, please keep your answers short.", True),
    ("Never talk to me while I'm in a ranked match.", True),
    ("Call me Oz.", True),
    ("Always answer in British English.", True),
    ("My dentist appointment is next Thursday at 4pm.", False),
    ("I always drink tea in the morning.", False),
])
def test_standing_instructions_are_recognised_from_his_words(words: str, standing: bool) -> None:
    from sora.runtime.remember_turn import is_standing

    plain = Remember(op="remember", title="Note", description="something")
    assert is_standing(plain, words) is standing


class Forgetful(Rememberer):
    """Never calls remember; files the fact as her own thought instead (seen live)."""

    def __init__(self) -> None:
        super().__init__()
        self.asked: list[str] = []

    async def choose_call(self, prompt: str, observations: str,
                          operations: frozenset[str]) -> CompanionCall:
        if "remember_thought" in operations and not self.done:
            self.done = True
            return CompanionCall.model_validate({
                "op": "remember_thought",
                "thought": "The user mentioned they are allergic to peanuts."})
        return CompanionCall.model_validate({"op": "finish"})

    async def choose_remember(self, prompt: str) -> Any:
        from sora.contracts.memory import RememberChoice

        self.asked.append(prompt)
        return RememberChoice(remember=True, title="Peanut allergy",
                              description="He is allergic to peanuts.")


@pytest.mark.asyncio
async def test_the_safety_net_keeps_a_fact_the_tool_missed(tmp_path: Path) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.save(SettingsEdit(version=10, expected_revision=0, changes={
        "perception.desktop_context": False, "perception.window_context": False,
        "perception.mode": "native-only"}))
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    await runtime.start()
    provider = Forgetful()
    settings.provider = provider
    runtime.dialogue_provider = provider
    try:
        with owner_local_scope():
            await runtime.dialogue("I'm allergic to peanuts.")
        await asyncio.gather(*runtime._memory_tasks)
        memories = await runtime.repository.list_memories(
            runtime.config.owner_id, project_id=runtime.config.project_id,
            observed_at=datetime.now(UTC))
        # The "thought" that only reported his fact was not kept as hers...
        assert [m.content for m in memories] == ["He is allergic to peanuts."]
        # ...and the focused question stored it as his memory, with the turn.
        assert provider.asked == ["I'm allergic to peanuts."]
        assert memories[0].title == "Peanut allergy"
        entry = read_entry(runtime.memory_entries_root(), memories[0].memory_id)
        assert entry is not None and entry.owner_text == "I'm allergic to peanuts."
    finally:
        await runtime.close()


def test_a_thought_that_echoes_his_words_is_not_hers() -> None:
    from sora.runtime.remember_turn import echoes

    assert echoes("I like lo-fi music when I code.", "I like lo-fi music when I code.")
    assert not echoes("I enjoyed planning the trip with him.", "We booked the cottage!")
