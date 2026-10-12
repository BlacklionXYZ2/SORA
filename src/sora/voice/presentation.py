"""Client-local P14.4 audio-clock and amplitude presentation primitives."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from enum import StrEnum

from sora.contracts.voice import VoiceEmotion, VoicePlaybackCommand

from .vowels import VOWELS, vowel_weights


class VoicePresentationResetReason(StrEnum):
    COMPLETED = "completed"
    PAUSED = "paused"
    INTERRUPTED = "interrupted"
    DEVICE_LOST = "device_lost"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SynthesizedAudioChunk:
    """One ordered local PCM chunk; bytes never cross the Core contract."""

    sequence: int
    pcm_s16le: bytes
    sample_rate: int = 24_000
    channels: int = 1

    def __post_init__(self) -> None:
        if not 0 <= self.sequence <= 1_000_000:
            raise ValueError("audio chunk sequence is out of range")
        if not 8_000 <= self.sample_rate <= 96_000:
            raise ValueError("audio sample rate is out of range")
        if self.channels not in {1, 2}:
            raise ValueError("audio must be mono or stereo")
        frame_width = 2 * self.channels
        if not self.pcm_s16le or len(self.pcm_s16le) % frame_width:
            raise ValueError("audio must contain complete non-empty signed-16 PCM frames")

    @property
    def sample_frames(self) -> int:
        return len(self.pcm_s16le) // (2 * self.channels)

    @property
    def duration_ms(self) -> float:
        return self.sample_frames * 1000.0 / self.sample_rate


@dataclass(frozen=True, slots=True)
class VoicePresentationFrame:
    """Local presentation sample derived from audio, never accepted from a model or Core API."""

    playback_id: str
    output_epoch: int
    sequence: int
    position_ms: float
    duration_ms: float
    mouth_open: float
    emotion: VoiceEmotion
    # A, E, I, O, U shares of the mouth shape, summing to 1; all zero in silence.
    vowels: tuple[float, ...] = (0.0,) * len(VOWELS)


class VoicePresentationClock:
    """Joins ordered PCM chunks to one playback identity and monotonic audio clock."""

    def __init__(
        self,
        *,
        noise_floor: float = 0.012,
        gain: float = 3.5,
        attack: float = 0.72,
        release: float = 0.38,
        vowel_blend: float = 0.6,
    ) -> None:
        if not 0 <= noise_floor < 1:
            raise ValueError("noise floor must be in [0, 1)")
        if not 0 < gain <= 20:
            raise ValueError("amplitude gain must be in (0, 20]")
        if not 0 < attack <= 1 or not 0 < release <= 1:
            raise ValueError("attack and release must be in (0, 1]")
        self.noise_floor = noise_floor
        self.gain = gain
        self.attack = attack
        self.release = release
        self.vowel_blend = vowel_blend
        self._playback_id: str | None = None
        self._output_epoch = 0
        self._emotion = VoiceEmotion.NEUTRAL
        self._next_sequence = 0
        self._position_ms = 0.0
        self._mouth_open = 0.0
        self._vowels = (0.0,) * len(VOWELS)

    @property
    def active(self) -> bool:
        return self._playback_id is not None

    @property
    def active_identity(self) -> tuple[str, int] | None:
        if self._playback_id is None:
            return None
        return self._playback_id, self._output_epoch

    def begin(self, command: VoicePlaybackCommand) -> None:
        if self.active:
            raise RuntimeError("voice presentation is already active")
        self._playback_id = command.playback_id
        self._output_epoch = command.output_epoch
        self._emotion = command.emotion
        self._next_sequence = 0
        self._position_ms = 0.0
        self._mouth_open = 0.0
        self._vowels = (0.0,) * len(VOWELS)

    def frame(
        self,
        command: VoicePlaybackCommand,
        chunk: SynthesizedAudioChunk,
    ) -> VoicePresentationFrame:
        if (
            self._playback_id != command.playback_id
            or self._output_epoch != command.output_epoch
        ):
            raise ValueError("audio chunk belongs to a stale playback identity")
        if chunk.sequence != self._next_sequence:
            raise ValueError("audio chunk sequence did not advance exactly once")
        rms = pcm_s16le_rms(chunk.pcm_s16le)
        target = min(1.0, max(0.0, (rms - self.noise_floor) * self.gain))
        blend = self.attack if target >= self._mouth_open else self.release
        self._mouth_open += (target - self._mouth_open) * blend
        heard = vowel_weights(chunk.pcm_s16le, chunk.sample_rate, chunk.channels)
        if any(heard):
            # Smooth between chunks so the mouth glides between vowels instead of snapping.
            mixed = [
                old + (new - old) * self.vowel_blend if any(self._vowels) else new
                for old, new in zip(self._vowels, heard, strict=True)
            ]
            total = sum(mixed)
            self._vowels = tuple(value / total for value in mixed)
        frame = VoicePresentationFrame(
            playback_id=command.playback_id,
            output_epoch=command.output_epoch,
            sequence=chunk.sequence,
            position_ms=self._position_ms,
            duration_ms=chunk.duration_ms,
            mouth_open=min(1.0, max(0.0, self._mouth_open)),
            emotion=self._emotion,
            vowels=self._vowels if any(heard) else (0.0,) * len(VOWELS),
        )
        self._next_sequence += 1
        self._position_ms += chunk.duration_ms
        return frame

    def reset(self) -> tuple[str, int] | None:
        identity = self.active_identity
        self._playback_id = None
        self._emotion = VoiceEmotion.NEUTRAL
        self._next_sequence = 0
        self._position_ms = 0.0
        self._mouth_open = 0.0
        self._vowels = (0.0,) * len(VOWELS)
        return identity


def pcm_s16le_rms(pcm: bytes) -> float:
    """Return normalized RMS for complete signed-16 little-endian samples."""

    if not pcm or len(pcm) % 2:
        raise ValueError("PCM must contain complete non-empty signed-16 samples")
    square_sum = 0.0
    count = 0
    for (sample,) in struct.iter_unpack("<h", pcm):
        normalized = sample / 32768.0
        square_sum += normalized * normalized
        count += 1
    return math.sqrt(square_sum / count)
