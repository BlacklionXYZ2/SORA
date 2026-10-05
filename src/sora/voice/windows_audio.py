"""Optional real local speech adapters. Importing Core never imports audio libraries."""

from __future__ import annotations

import asyncio
import importlib
import re
import threading
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

from .client import AudioFrame, TranscriptHypothesis, VadDecision
from .presentation import SynthesizedAudioChunk
from .settings import VoiceSettings


class PressToTalkVad:
    """Explicit user-held boundary; silence is retained, not compressed by a VAD."""

    def process(self, frame: AudioFrame) -> VadDecision:
        return VadDecision(speech=bool(frame.pcm_s16le), utterance_ended=not frame.pcm_s16le)

    def reset(self) -> None:
        pass


class WhisperStt:
    def __init__(self, model: Any, limit_seconds: int) -> None:
        self.model = model
        self.limit = limit_seconds * 16000 * 2
        self.buffer = bytearray()
        self.started: Any = None
        self.generation = 0
        self.lock = threading.Lock()

    @classmethod
    def load(cls, settings: VoiceSettings) -> WhisperStt:
        library = importlib.import_module("faster_whisper")
        model = library.WhisperModel(
            settings.stt_model_path,
            device="cpu",
            compute_type="int8",
            cpu_threads=6,
            local_files_only=True,
        )
        return cls(model, settings.recording_limit_seconds)

    async def process(
        self, frame: AudioFrame, *, utterance_ended: bool
    ) -> TranscriptHypothesis | None:
        if frame.sample_rate != 16000 or frame.channels != 1 or len(frame.pcm_s16le) % 2:
            raise ValueError("Whisper requires complete mono 16 kHz signed-16 PCM")
        if self.started is None:
            self.started = frame.captured_at
        self.buffer.extend(frame.pcm_s16le)
        if len(self.buffer) > self.limit:
            self.reset()
            raise ValueError("Press-to-talk recording exceeded its configured limit")
        if not utterance_ended:
            return None
        audio, started, generation = bytes(self.buffer), self.started, self.generation
        self.buffer.clear()
        self.started = None
        if len(audio) < 3200:
            raise ValueError("No usable speech captured. Hold to talk for at least 0.1 seconds.")

        def transcribe() -> tuple[str, float | None, float]:
            # A cancelled to_thread call cannot stop native inference. Serialise actual calls
            # and reject its result by generation; never run a second model concurrently.
            with self.lock:
                np = importlib.import_module("numpy")
                samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768
                if float(np.sqrt(np.mean(samples * samples))) < 0.001:
                    raise ValueError("No audible speech captured. Nothing was sent to SORA.")
                segments, _ = self.model.transcribe(
                    samples, language="en", beam_size=1, word_timestamps=True, vad_filter=False
                )
                text, reference, probabilities = [], None, []
                for segment in segments:
                    if segment.no_speech_prob > 0.6:
                        continue
                    text.append(segment.text)
                    for word in segment.words or ():
                        probabilities.append(float(word.probability))
                        if reference is None and word.word.strip().casefold() in {
                            "this",
                            "that",
                            "here",
                            "there",
                        }:
                            reference = float(word.start)
                confidence = sum(probabilities) / len(probabilities) if probabilities else 0.0
                return " ".join(text).strip(), reference, confidence

        text, offset, confidence = await asyncio.to_thread(transcribe)
        if generation != self.generation:
            raise asyncio.CancelledError
        if not text:
            raise ValueError("No speech recognized. Nothing was sent to SORA.")
        return TranscriptHypothesis(
            text=text,
            confidence=max(0.0, min(1.0, confidence)),
            final=True,
            reference_spoken_at=(
                started + timedelta(seconds=offset) if offset is not None else None
            ),
        )

    def reset(self) -> None:
        self.generation += 1
        self.buffer.clear()
        self.started = None


class KokoroTts:
    def __init__(self, model: Any, speed: float) -> None:
        self.model = model
        self.speed = speed
        self.lock = threading.Lock()

    @classmethod
    def load(cls, settings: VoiceSettings) -> KokoroTts:
        library = importlib.import_module("kokoro_onnx")
        return cls(
            library.Kokoro(settings.tts_model_path, settings.voices_path), settings.speech_speed
        )

    async def synthesize(self, text: str, *, voice_id: str) -> AsyncIterator[SynthesizedAudioChunk]:
        # Keep full evidence in the transcript; don't read the technical source footer aloud.
        speech = text.split("\n\nRead evidence:", 1)[0]
        speech = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", speech)
        speech = re.sub(r"[`*#]", "", speech).strip()
        if not speech:
            raise ValueError("Reply contains no speakable text")
        sequence = 0
        # Bound each synthesis call for useful first-audio latency and interruption.
        parts = re.findall(r".{1,350}(?:\s+|$)|\S{1,350}", speech, re.DOTALL)
        for part in parts:

            def create(segment: str = part) -> bytes:
                with self.lock:
                    np = importlib.import_module("numpy")
                    samples, rate = self.model.create(
                        segment, voice=voice_id, speed=self.speed, lang="en-us"
                    )
                    if rate != 24000:
                        raise ValueError("Kokoro must produce mono 24 kHz output")
                    return bytes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())

            pcm = await asyncio.to_thread(create)
            for position in range(0, len(pcm), 4800):
                chunk = pcm[position : position + 4800]
                if chunk:
                    yield SynthesizedAudioChunk(sequence=sequence, pcm_s16le=chunk)
                    sequence += 1


def audio_devices(sd: Any) -> list[dict[str, Any]]:
    hosts = sd.query_hostapis()
    return [
        {
            "key": f"{hosts[d['hostapi']]['name']}:{d['name']}",
            "index": i,
            "input_channels": int(d["max_input_channels"]),
            "output_channels": int(d["max_output_channels"]),
        }
        for i, d in enumerate(sd.query_devices())
    ]


def resolve_device(sd: Any, key: str, *, input_device: bool) -> int:
    channel_key = "input_channels" if input_device else "output_channels"
    if not key:
        index = int(sd.default.device[0 if input_device else 1])
        if index < 0:
            raise ValueError(
                "Windows has no default microphone/speaker. Select a device in Settings."
            )
        return index
    matches = [d for d in audio_devices(sd) if d["key"] == key and d[channel_key] > 0]
    if len(matches) != 1:
        raise ValueError(
            "Configured audio device is missing or ambiguous. Choose its current key in Settings."
        )
    return int(matches[0]["index"])


class SoundDevicePlayback:
    def __init__(self, sd: Any, device: int) -> None:
        self.sd, self.device = sd, device
        self.stream: Any = None
        self.lock = threading.Lock()

    async def start(self, playback_id: str, *, output_device_id: str) -> None:
        del playback_id, output_device_id
        self.stream = self.sd.RawOutputStream(
            samplerate=24000, channels=1, dtype="int16", device=self.device, blocksize=2400
        )
        self.stream.start()

    async def write(self, chunk: bytes) -> None:
        stream = self.stream
        if stream is None:
            raise RuntimeError("Speaker stream is closed")

        def write() -> None:
            # Cancelling to_thread doesn't stop native Pa_WriteStream. Close must wait
            # for this short (normally <=100ms) write rather than free its live handle.
            with self.lock:
                if self.stream is stream:
                    stream.write(chunk)

        await asyncio.to_thread(write)

    async def finish(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:

            def finish() -> None:
                with self.lock:
                    try:
                        stream.stop()
                    finally:
                        stream.close()

            await asyncio.to_thread(finish)

    async def abort(self) -> None:
        stream, self.stream = self.stream, None
        if stream is not None:

            def abort() -> None:
                with self.lock:
                    try:
                        stream.abort()
                    finally:
                        stream.close()

            await asyncio.to_thread(abort)
