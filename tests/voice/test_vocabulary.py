"""The speech recogniser expects her wake word and her agents' names ("Claude", not "cloud")."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.voice.vocabulary import MAX_NAMES, hotwords
from sora.voice.windows_audio import WhisperStt

ROOT = Path(__file__).resolve().parents[2]


def test_hotwords_put_the_wake_word_first_and_drop_duplicates_and_junk() -> None:
    assert hotwords("sora, hey sora", ["Claude", "Cody", "claude", "", 7, "x" * 41]) == (
        "Sora, Claude, Cody")
    assert hotwords("", []) is None
    many = hotwords("sora", [f"Agent{index}" for index in range(30)])
    assert many is not None and len(many.split(", ")) == MAX_NAMES


def test_core_offers_the_agents_names_to_the_voice_worker(tmp_path: Path) -> None:
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                          provider=DeterministicProvider())
    names = runtime.local_voice.vocabulary()
    assert {"Claude", "Cody", "Hermes", "Aggie"} <= set(names)


def test_press_to_talk_and_listening_pass_the_names_to_whisper() -> None:
    pytest.importorskip("numpy")
    seen: list[Any] = []

    def transcribe(samples: Any, **kwargs: Any) -> tuple[list[Any], None]:
        seen.append(kwargs.get("hotwords"))
        word = SimpleNamespace(word=" Claude", probability=0.9, start=0.0)
        return [SimpleNamespace(text=" Walk to the Claude window", no_speech_prob=0.0,
                                words=[word])], None

    stt = WhisperStt(SimpleNamespace(transcribe=transcribe), 5)
    stt.hotwords = "Sora, Claude"
    loud = (b"\x00\x40" * 8000)
    asyncio.run(stt.transcribe_segment(loud, datetime.now(UTC), hotwords=stt.hotwords))
    assert seen == ["Sora, Claude"]
