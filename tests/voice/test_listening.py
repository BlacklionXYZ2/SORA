"""Always-on listening logic: segmenting speech and deciding whether it is for SORA."""

from __future__ import annotations

import base64
import io
import wave
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from sora.voice.listening import (
    Addressee,
    Frame,
    RollingBuffer,
    Segment,
    SpeechSegmenter,
    wake_pattern,
    wav_base64,
)

T0 = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


def frames(probabilities: list[float]) -> list[tuple[Frame, float]]:
    return [
        (Frame(T0 + timedelta(milliseconds=100 * index), bytes([index % 256]) * 3200), p)
        for index, p in enumerate(probabilities)
    ]


def run(segmenter: SpeechSegmenter, probabilities: list[float]) -> list[Segment]:
    return [s for f, p in frames(probabilities) if (s := segmenter.push(f, p)) is not None]


def test_speech_becomes_one_segment_with_pre_roll_and_trimmed_tail() -> None:
    silence, speech = [0.0] * 10, [0.9] * 12
    [segment] = run(SpeechSegmenter(), silence + speech + [0.0] * 8 + silence)
    # Starts 3 pre-roll frames before speech was confirmed (frame 10 + 1 - 4 = frame 7).
    assert segment.started_at == T0 + timedelta(milliseconds=700)
    # 3 pre-roll + 12 speech + 2 of the 8 silent frames kept.
    assert round(segment.seconds, 6) == round((3 + 12 + 2) * 0.1, 6)


def test_a_cough_is_dropped_and_a_short_pause_does_not_split_a_sentence() -> None:
    assert run(SpeechSegmenter(), [0.0] * 5 + [0.9] * 2 + [0.0] * 12) == []
    sentence = [0.9] * 10 + [0.1] * 5 + [0.9] * 10 + [0.0] * 8
    assert len(run(SpeechSegmenter(), [0.0] * 5 + sentence)) == 1


def test_long_speech_is_cut_at_the_limit() -> None:
    segments = run(SpeechSegmenter(max_seconds=2), [0.9] * 50)
    assert len(segments) == 2 and all(s.seconds <= 2.1 for s in segments)


def test_the_rolling_buffer_keeps_only_recent_audio() -> None:
    buffer = RollingBuffer(seconds=1)
    for frame, _ in frames([0.0] * 25):
        buffer.add(frame)
    assert len(buffer.frames) == 10 and buffer.last(2)[-1].captured_at.second == 2


def test_her_name_or_the_follow_on_window_means_she_is_addressed() -> None:
    addressee = Addressee(wake_words="sora, zora", follow_on_seconds=8)
    later = T0 + timedelta(seconds=30)
    assert addressee.heard("What do you think, Sora?", ended_at=later, speaking=False)[0]
    assert addressee.heard("zora what time is it", ended_at=later, speaking=False)[0]
    assert not addressee.heard("I'm on the phone with Sorana", ended_at=later, speaking=False)[0]
    assert not addressee.heard("Pass me the salt", ended_at=later, speaking=False)[0]
    addressee.exchanged(later)
    assert addressee.heard("And tomorrow?", ended_at=later + timedelta(seconds=5),
                           speaking=False) == (True, "follow-on after her reply")
    assert not addressee.heard("And tomorrow?", ended_at=later + timedelta(seconds=20),
                               speaking=False)[0]


def test_while_she_speaks_only_her_name_counts_and_never_her_own_voice() -> None:
    addressee = Addressee()
    own = ["Hi, I'm Sora, your desktop companion. How can I help?"]
    assert not addressee.heard("how can I help", ended_at=T0, speaking=True, her_words=own)[0]
    assert not addressee.heard("I'm Sora your desktop companion", ended_at=T0, speaking=True,
                               her_words=own)[0]
    assert addressee.heard("Sora, stop", ended_at=T0, speaking=True, her_words=own)[0]
    # A bare "stop" interrupts too, but not when it is her own word through the speakers.
    assert addressee.heard("Stop!", ended_at=T0, speaking=True, her_words=own) == (
        True, "asked to stop")
    assert not addressee.heard("Stop.", ended_at=T0, speaking=True,
                               her_words=["Stop. Let me think about that."])[0]
    assert not addressee.heard("Stop the music", ended_at=T0, speaking=True, her_words=own)[0]


def test_wake_words_and_wav() -> None:
    assert wake_pattern("hey sora").search("HEY   SORA, lights") is not None
    assert wake_pattern(" , ").search("sora") is not None  # empty setting falls back to her name
    raw = base64.b64decode(wav_base64(b"\x00\x01" * 1600))
    with wave.open(io.BytesIO(raw)) as reader:
        shape = (reader.getnchannels(), reader.getframerate(), reader.getnframes())
    assert shape == (1, 16000, 1600)


def test_settings_saved_before_listening_existed_still_load(tmp_path: Path) -> None:
    import json

    from sora.runtime.app_settings import AppSettings, AppSettingsStore
    from sora.voice.settings import LISTENING_FIELDS

    payload = AppSettings().model_dump(mode="json")
    for name in LISTENING_FIELDS:
        del payload["voice"][name]
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    voice = AppSettingsStore(path).load().voice
    assert (voice.listening, voice.wake_words, voice.follow_on_seconds, voice.audio_route) == (
        "always", "sora", 8, "auto",
    )
    payload["voice"]["unknown"] = 1
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="complete local voice settings"):
        AppSettingsStore(path).load()


@pytest.mark.asyncio
@pytest.mark.parametrize("listening,voice,expected", [
    ("always", True, True), ("press", True, False), ("always", False, False),
])
async def test_owner_launch_starts_listening_only_when_settings_allow(
    tmp_path: Path, listening: str, voice: bool, expected: bool,
) -> None:
    from unittest.mock import AsyncMock

    from sora.providers.mock import DeterministicProvider
    from sora.runtime.app_settings import AppSettings, AppSettingsController
    from sora.runtime.service import RuntimeConfig, SoraRuntime

    root = Path(__file__).resolve().parents[2]
    settings = AppSettingsController(tmp_path, AppSettings.model_validate({
        "voice": {"listening": listening}, "local_companion": {"voice": voice},
    }))
    runtime = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=root / "identity"),
                          provider=DeterministicProvider(), app_settings=settings)
    start = AsyncMock()
    runtime.local_voice.start = start  # type: ignore[method-assign]
    runtime.start_listening_on_launch()
    if runtime._listen_on_launch is not None:
        await runtime._listen_on_launch
    assert start.await_count == (1 if expected else 0)
