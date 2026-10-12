"""Always-on listening: find speech in the open microphone and decide whether it is for SORA.

Pure logic, so it is tested without a microphone; the voice worker feeds it 100 ms frames.
docs/plans/ALWAYS_ON_LISTENING_2026-10-08.md describes the whole chain:

    microphone -> voice activity -> segment -> transcript -> addressed to SORA? -> brain

Each model is a swappable slot. Voice activity uses the Silero model bundled with
faster-whisper (no download). "Addressed" is the wake word in Whisper's transcript, or speech
within a short follow-on window after she has spoken; a trained System-1 addressee model can
replace it later. Audio stays in memory: nothing here writes to disk.
"""

from __future__ import annotations

import base64
import io
import re
import wave
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sora.contracts.voice import VoiceConversationIntent

from .intents import classify_voice_intent

FRAME_SAMPLES = 1600  # 100 ms at 16 kHz
SAMPLE_RATE = 16_000


@dataclass(frozen=True)
class Frame:
    captured_at: datetime
    pcm_s16le: bytes


@dataclass(frozen=True)
class Segment:
    """One stretch of speech, with a little audio from before it began."""

    started_at: datetime
    ended_at: datetime
    pcm_s16le: bytes

    @property
    def seconds(self) -> float:
        return len(self.pcm_s16le) / (2 * SAMPLE_RATE)


class RollingBuffer:
    """The last few seconds of microphone audio, in memory only."""

    def __init__(self, seconds: float = 60) -> None:
        self.frames: deque[Frame] = deque(maxlen=max(1, int(seconds * 10)))

    def add(self, frame: Frame) -> None:
        self.frames.append(frame)

    def last(self, count: int) -> list[Frame]:
        return list(self.frames)[-count:] if count > 0 else []

    def clear(self) -> None:
        self.frames.clear()


@dataclass
class SpeechSegmenter:
    """Turns per-frame speech probabilities into utterances.

    Speech starts after ``start_frames`` frames at or above ``on``; it ends after
    ``end_frames`` frames below ``off`` (a pause), or at ``max_seconds``. ``pre_roll`` frames
    from before the start are included so the first syllable is not clipped. Very short bursts
    (a cough, a click) are dropped.
    """

    on: float = 0.5
    off: float = 0.35
    start_frames: int = 2
    end_frames: int = 8
    pre_roll: int = 3
    min_speech_frames: int = 4
    max_seconds: float = 30
    _recent: deque[Frame] = field(default_factory=lambda: deque(maxlen=16))
    _active: list[Frame] = field(default_factory=list)
    _speech_frames: int = 0
    _above: int = 0
    _below: int = 0

    def reset(self) -> None:
        self._recent.clear()
        self._active.clear()
        self._speech_frames = self._above = self._below = 0

    @property
    def hearing(self) -> bool:
        return bool(self._active)

    def push(self, frame: Frame, probability: float) -> Segment | None:
        if not self._active:
            self._recent.append(frame)
            self._above = self._above + 1 if probability >= self.on else 0
            if self._above < self.start_frames:
                return None
            # Speech began: keep the pre-roll and the frames that confirmed it.
            keep = self.pre_roll + self.start_frames
            self._active = list(self._recent)[-keep:]
            self._recent.clear()
            self._speech_frames = self.start_frames
            self._below = 0
            return None
        self._active.append(frame)
        if probability >= self.off:
            self._below = 0
            self._speech_frames += 1
        else:
            self._below += 1
        too_long = len(self._active) >= self.max_seconds * 10
        if self._below < self.end_frames and not too_long:
            return None
        frames, self._active = self._active, []
        speech, self._speech_frames, self._above, self._below = self._speech_frames, 0, 0, 0
        if speech < self.min_speech_frames:
            return None
        if not too_long:
            frames = frames[: len(frames) - self.end_frames + 2]  # trim most trailing silence
        return Segment(
            started_at=frames[0].captured_at,
            ended_at=frames[-1].captured_at + timedelta(milliseconds=100),
            pcm_s16le=b"".join(item.pcm_s16le for item in frames),
        )


def wake_pattern(words: str) -> re.Pattern[str]:
    """Settings give comma-separated names ("sora, zora"); match each as a whole word."""
    names = [name.strip() for name in words.split(",") if name.strip()]
    if not names:
        names = ["sora"]
    return re.compile(
        r"\b(?:" + "|".join(re.escape(name).replace(r"\ ", r"\s+") for name in names) + r")\b",
        re.IGNORECASE,
    )


def _words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z']+", text.casefold()) if len(word) > 2}


@dataclass
class Addressee:
    """Is this utterance for SORA? Rules first; a trained System-1 model can replace this slot.

    * Her name anywhere in the utterance means yes ("Sora, what's this?", "what do you think,
      Sora?").
    * Within ``follow_on_seconds`` after she last spoke or was spoken to, yes without the name,
      so a conversation can continue naturally.
    * While she is speaking through the speakers, the microphone hears her own voice. Then only
      her name counts, or a bare request to stop ("stop", "be quiet", "hold on"), and not when
      the words are mostly what she is saying herself (so she does not interrupt herself by
      saying "I'm Sora").
    """

    wake_words: str = "sora"
    follow_on_seconds: float = 8
    clock: Callable[[], datetime] | None = None
    last_exchange: datetime | None = None

    def __post_init__(self) -> None:
        self.pattern = wake_pattern(self.wake_words)

    def heard(
        self, text: str, *, ended_at: datetime, speaking: bool, her_words: Sequence[str] = (),
    ) -> tuple[bool, str]:
        """Return (addressed, reason)."""
        named = bool(self.pattern.search(text))
        if speaking:
            stop = classify_voice_intent(text) is VoiceConversationIntent.STOP_SPEAKING
            if not named and not stop:
                return False, "she was speaking and was not addressed by name"
            own = _words(" ".join(her_words))
            said = _words(text)
            if said and own and len(said & own) / len(said) >= 0.6:
                return False, "this was her own voice through the speakers"
            return True, "named while she was speaking" if named else "asked to stop"
        if named:
            return True, "named"
        if (
            self.follow_on_seconds > 0
            and self.last_exchange is not None
            and timedelta(0)
            <= ended_at - self.last_exchange
            <= timedelta(seconds=self.follow_on_seconds) + _segment_slack(text)
        ):
            return True, "follow-on after her reply"
        return False, "not addressed"

    def exchanged(self, at: datetime) -> None:
        """She spoke, or was spoken to: start (or restart) the follow-on window."""
        self.last_exchange = at


def _segment_slack(text: str) -> timedelta:
    # The window is measured to when speech ends; a long sentence that began inside the window
    # still counts. About 0.4 s per word, capped.
    return timedelta(seconds=min(10.0, 0.4 * len(text.split())))


def wav_base64(pcm_s16le: bytes, *, sample_rate: int = SAMPLE_RATE) -> str:
    """Mono 16-bit WAV, base64-encoded, for brains that hear audio natively."""
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(pcm_s16le)
    return base64.b64encode(output.getvalue()).decode("ascii")


class SileroSpeechProbability:
    """Speech probability for the newest 100 ms, from faster-whisper's bundled Silero model.

    The model is scored over a sliding one-second window each frame, so it always has context;
    the frame's probability is the highest of the windows covering it. Imports are lazy so this
    module loads without NumPy.
    """

    WINDOW = 512
    SPAN = 32 * 512  # 1.024 s

    def __init__(self) -> None:
        import importlib

        self.np = importlib.import_module("numpy")
        vad = importlib.import_module("faster_whisper.vad")
        self.model = vad.get_vad_model()
        self.samples = self.np.zeros(self.SPAN, dtype="float32")

    def __call__(self, pcm_s16le: bytes) -> float:
        np = self.np
        new = np.frombuffer(pcm_s16le, dtype="<i2").astype("float32") / 32768
        self.samples = np.concatenate([self.samples, new])[-self.SPAN:]
        probabilities = self.model(self.samples).reshape(-1)
        covering = max(1, -(-len(new) // self.WINDOW))
        return float(probabilities[-covering:].max())

    def reset(self) -> None:
        self.samples[:] = 0
