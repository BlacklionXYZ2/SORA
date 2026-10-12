"""Sentence-first speech, prefetching synthesis and five-vowel lip sync."""

from __future__ import annotations

import asyncio
import math
import struct
import sys
import time
import types
from typing import Any

import pytest

from sora.contracts.voice import VoiceEmotion, VoicePlaybackCommand
from sora.voice.presentation import SynthesizedAudioChunk, VoicePresentationClock
from sora.voice.relay import LocalPresentationPacket
from sora.voice.vowels import VOWEL_FORMANTS, VOWELS, vowel_weights
from sora.voice.windows_audio import FIRST_SEGMENT_CHARS, KokoroTts, speech_segments


def synthetic_vowel(f1: float, f2: float, *, pitch: float = 210.0, ms: int = 100) -> bytes:
    """A glottal pulse train through three formant resonators, like a sung vowel."""

    rate = 24_000
    signal = [0.0] * (rate * ms // 1000)
    position = 0.0
    while position < len(signal):
        signal[int(position)] = 1.0
        position += rate / pitch
    for centre, bandwidth in ((f1, 90.0), (f2, 110.0), (2900.0, 160.0)):
        radius = math.exp(-math.pi * bandwidth / rate)
        a1, a2 = 2 * radius * math.cos(2 * math.pi * centre / rate), -radius * radius
        previous = before = 0.0
        filtered = []
        for value in signal:
            current = value + a1 * previous + a2 * before
            filtered.append(current)
            before, previous = previous, current
        signal = filtered
    peak = max(abs(value) for value in signal)
    return b"".join(struct.pack("<h", int(value / peak * 12_000)) for value in signal)


def test_first_segment_is_one_short_sentence_and_later_ones_are_grouped() -> None:
    segments = speech_segments(
        "Hi there! I looked at your screen. Spotify is open, and the song is paused. Sure."
    )
    assert segments == [
        "Hi there!",
        "I looked at your screen. Spotify is open, and the song is paused. Sure.",
    ]
    grown = speech_segments("A. " + "This sentence is forty characters long. " * 9)
    assert [len(segment) for segment in grown] == [2, 119, 239]


def test_long_first_sentence_is_cut_at_a_clause() -> None:
    sentence = "Okay, " + "this goes on and on " * 12 + "until it ends."
    first, *rest = speech_segments(sentence)
    assert len(first) <= FIRST_SEGMENT_CHARS
    assert sentence.startswith(first) and sentence[len(first)] == " "  # not mid-word
    assert " ".join([first, *rest]).split() == sentence.split()


def test_line_breaks_end_segments() -> None:
    assert speech_segments("Line one\nLine two.") == ["Line one", "Line two."]


class SlowFakeKokoro:
    """Takes 0.15 s per segment, returns 0.1 s of audio per character."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def create(self, text: str, **_: Any) -> tuple[list[float], int]:
        self.calls.append((text, time.perf_counter()))
        time.sleep(0.15)
        return [0.25] * (2400 * len(text)), 24_000


class FakeNumpy(types.ModuleType):
    @staticmethod
    def clip(samples: list[float], low: float, high: float) -> FakeArray:
        return FakeArray([min(high, max(low, value)) for value in samples])


class FakeArray(list[float]):
    def __mul__(self, scale: object) -> FakeArray:
        assert isinstance(scale, int)
        return FakeArray([value * scale for value in self])

    def astype(self, _: str) -> FakeArray:
        return self

    def tobytes(self) -> bytes:
        return b"".join(struct.pack("<h", int(value)) for value in self)


@pytest.fixture
def fake_numpy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "numpy", FakeNumpy("numpy"))


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_numpy")
async def test_first_audio_arrives_before_later_sentences_are_synthesised() -> None:
    model = SlowFakeKokoro()
    tts = KokoroTts(model, 1.0)
    started = time.perf_counter()
    stream = tts.synthesize("Hi! Second sentence here. Third one.", voice_id="af_heart")
    first = await anext(stream)
    first_audio = time.perf_counter() - started
    assert first.sequence == 0
    assert first_audio < 0.3  # one segment, not the whole reply
    chunks = [first] + [chunk async for chunk in stream]
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))
    assert [text for text, _ in model.calls] == ["Hi!", "Second sentence here. Third one."]
    # The second segment was synthesised while the first was being consumed.
    assert model.calls[1][1] - model.calls[0][1] < 0.3


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_numpy")
async def test_closing_the_stream_stops_further_synthesis() -> None:
    model = SlowFakeKokoro()
    tts = KokoroTts(model, 1.0)
    stream = tts.synthesize("One. Two three four. " + "More words here. " * 40, voice_id="v")
    await anext(stream)
    await stream.aclose()
    await asyncio.sleep(0.5)
    assert len(model.calls) <= 3


@pytest.mark.asyncio
@pytest.mark.usefixtures("fake_numpy")
async def test_a_failed_later_segment_raises_after_earlier_audio() -> None:
    class FailsSecond(SlowFakeKokoro):
        def create(self, text: str, **kwargs: Any) -> tuple[list[float], int]:
            if self.calls:
                raise RuntimeError("synthesis failed")
            return super().create(text, **kwargs)

    tts = KokoroTts(FailsSecond(), 1.0)
    received = []
    with pytest.raises(RuntimeError, match="synthesis failed"):
        async for chunk in tts.synthesize("First. Second.", voice_id="v"):
            received.append(chunk)
    assert received


@pytest.mark.parametrize("pitch", [120.0, 210.0])
@pytest.mark.parametrize("vowel", VOWELS)
def test_vowel_estimate_matches_synthetic_vowels(vowel: str, pitch: float) -> None:
    f1, f2 = VOWEL_FORMANTS[vowel]
    scale = 0.9 if pitch < 150 else 1.0  # lower voices have slightly lower formants
    weights = vowel_weights(synthetic_vowel(f1 * scale, f2 * scale, pitch=pitch), 24_000)
    assert math.isclose(sum(weights), 1.0)
    assert VOWELS[weights.index(max(weights))] == vowel


def test_silence_has_no_vowel() -> None:
    assert vowel_weights(b"\x00\x00" * 2400, 24_000) == (0.0,) * 5


def test_presentation_frames_carry_vowels_and_validate_in_the_relay() -> None:
    clock = VoicePresentationClock()
    command = VoicePlaybackCommand.model_construct(
        playback_id="p", output_epoch=1, emotion=VoiceEmotion.NEUTRAL
    )
    clock.begin(command)
    f1, f2 = VOWEL_FORMANTS["i"]
    frame = clock.frame(command, SynthesizedAudioChunk(0, synthetic_vowel(f1, f2)))
    assert frame.vowels.index(max(frame.vowels)) == VOWELS.index("i")
    silent = clock.frame(command, SynthesizedAudioChunk(1, b"\x00\x00" * 2400))
    assert silent.vowels == (0.0,) * 5
    packet = LocalPresentationPacket.model_validate(
        {"op": "frame", "playback_id": "p", "output_epoch": 1, "vowels": frame.vowels}
    )
    assert len(packet.vowels) == 5
    with pytest.raises(ValueError):
        LocalPresentationPacket.model_validate(
            {"op": "frame", "playback_id": "p", "output_epoch": 1, "vowels": [1.5, 0, 0, 0, 0]}
        )
