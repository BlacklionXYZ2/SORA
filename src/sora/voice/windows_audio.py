"""Optional real local speech adapters. Importing Core never imports audio libraries."""

from __future__ import annotations

import asyncio
import importlib
import os
import re
import threading
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing
from datetime import datetime, timedelta
from typing import Any

from .client import AudioFrame, TranscriptHypothesis, VadDecision
from .listening import wav_base64
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
        # Set by the worker when Settings route voice to brains that hear audio natively.
        self.attach_audio = False
        # Names to expect (sora.voice.vocabulary.hotwords), for press-to-talk and listening.
        self.hotwords: str | None = None

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

        text, offset, confidence = await asyncio.to_thread(
            self._transcribe, audio, self.hotwords,
        )
        if generation != self.generation:
            raise asyncio.CancelledError
        if not text:
            raise ValueError("No speech recognized. Nothing was sent to SORA.")
        return self._hypothesis(text, confidence, started, offset, audio)

    async def transcribe_segment(
        self, audio: bytes, started: datetime, *, hotwords: str | None = None,
    ) -> TranscriptHypothesis | None:
        """Always-on listening: transcribe one found segment; None when nothing was said.

        ``hotwords`` biases recognition toward her name, so "Sora" is not heard as "Sarah".
        """
        generation = self.generation
        try:
            text, offset, confidence = await asyncio.to_thread(self._transcribe, audio, hotwords)
        except ValueError:
            return None  # silence or noise: nothing to hear
        if generation != self.generation or not text:
            return None
        return self._hypothesis(text, confidence, started, offset, audio)

    def _hypothesis(
        self, text: str, confidence: float, started: datetime, offset: float | None,
        audio: bytes,
    ) -> TranscriptHypothesis:
        return TranscriptHypothesis(
            text=text,
            confidence=max(0.0, min(1.0, confidence)),
            final=True,
            reference_spoken_at=(
                started + timedelta(seconds=offset) if offset is not None else None
            ),
            audio_wav_base64=wav_base64(audio) if self.attach_audio else None,
        )

    def _transcribe(self, audio: bytes, hotwords: str | None) -> tuple[str, float | None, float]:
        # A cancelled to_thread call cannot stop native inference. Serialise actual calls
        # and reject its result by generation; never run a second model concurrently.
        with self.lock:
            np = importlib.import_module("numpy")
            samples = np.frombuffer(audio, dtype="<i2").astype(np.float32) / 32768
            if float(np.sqrt(np.mean(samples * samples))) < 0.001:
                raise ValueError("No audible speech captured. Nothing was sent to SORA.")
            segments, _ = self.model.transcribe(
                samples, language="en", beam_size=1, word_timestamps=True, vad_filter=False,
                hotwords=hotwords,
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

    def _create(self, segment: str, voice_id: str) -> bytes:
        with self.lock:
            np = importlib.import_module("numpy")
            samples, rate = self.model.create(
                segment, voice=voice_id, speed=self.speed, lang="en-us"
            )
            if rate != 24000:
                raise ValueError("Kokoro must produce mono 24 kHz output")
            return bytes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())

    async def synthesize(
        self, text: str, *, voice_id: str
    ) -> AsyncGenerator[SynthesizedAudioChunk]:
        # Keep full evidence in the transcript; don't read the technical source footer aloud.
        speech = speakable(text.split("\n\nRead evidence:", 1)[0])
        if not speech:
            raise ValueError("Reply contains no speakable text")

        async def whole() -> AsyncIterator[str]:
            yield speech

        async with aclosing(self.synthesize_stream(whole(), voice_id=voice_id)) as stream:
            async for chunk in stream:
                yield chunk

    async def synthesize_stream(
        self, texts: AsyncIterator[str], *, voice_id: str
    ) -> AsyncGenerator[SynthesizedAudioChunk]:
        """Speak text that arrives piece by piece, such as sentences of a reply being written."""
        # Speak the first sentence as soon as it is ready, and synthesise the next segment
        # while the current one plays, so later sentences arrive without a gap.
        ready: asyncio.Queue[bytes | BaseException | None] = asyncio.Queue(maxsize=2)

        async def produce() -> None:
            try:
                first = FIRST_SEGMENT_CHARS
                async for text in texts:
                    # Only the very first piece is cut short; later sentences stay whole.
                    for segment in speech_segments(speakable(text), first_limit=first):
                        await ready.put(await asyncio.to_thread(self._create, segment, voice_id))
                    first = SEGMENT_CHARS
                await ready.put(None)
            except Exception as exc:  # Delivered in order, after audio already queued.
                await ready.put(exc)

        producer = asyncio.create_task(produce(), name="sora-tts-prefetch")
        sequence = 0
        try:
            while (pcm := await ready.get()) is not None:
                if isinstance(pcm, BaseException):
                    raise pcm
                for position in range(0, len(pcm), 4800):
                    chunk = pcm[position : position + 4800]
                    if chunk:
                        yield SynthesizedAudioChunk(sequence=sequence, pcm_s16le=chunk)
                        sequence += 1
        finally:
            producer.cancel()
            await asyncio.gather(producer, return_exceptions=True)


def speakable(text: str) -> str:
    """Link labels instead of URLs, and no markdown symbols read aloud."""
    text = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", text)
    return re.sub(r"[`*#]", "", text).strip()


# Kokoro's time grows faster than linearly with length, so the first piece she says is cut at
# a clause near 90 characters: on 2026-10-07 a 100-character opener took 1.7 s, a 65 one 0.7 s.
FIRST_SEGMENT_CHARS = 90
SEGMENT_CHARS = 350


def speech_segments(speech: str, first_limit: int = FIRST_SEGMENT_CHARS) -> list[str]:
    """Split speech at sentence ends; keep the first segment short for fast first audio."""

    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?…])[\"')\]]*\s+|\n+", speech)
        if part and part.strip()
    ]
    segments: list[str] = []
    for sentence in sentences:
        limit = first_limit if not segments else SEGMENT_CHARS
        # The first segment is spoken alone. Later ones group sentences, growing from 120
        # characters so each is synthesised while the previous one is still playing.
        group = min(SEGMENT_CHARS, 120 * 2 ** (len(segments) - 2))
        if len(segments) > 1 and len(segments[-1]) + 1 + len(sentence) <= group:
            segments[-1] = f"{segments[-1]} {sentence}"
            continue
        while len(sentence) > limit:
            cut = _clause_cut(sentence, limit)
            segments.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
            limit = SEGMENT_CHARS
        if sentence:
            segments.append(sentence)
    return segments


def _clause_cut(sentence: str, limit: int) -> int:
    """Prefer a comma or semicolon, then a space, then a hard cut, at or before ``limit``."""

    window = sentence[: limit + 1]
    for marks in (",;:—", " "):
        cut = max(window.rfind(mark) for mark in marks)
        if cut >= limit // 3:
            return cut + 1
    return limit


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


def keep_full_cpu_speed() -> bool:
    """Opt this process out of Windows 11 power throttling (EcoQoS).

    The voice worker has no window, so Windows treats it as background work and moves it to
    efficiency cores after a couple of seconds. Measured on the owner's PC (2026-10-07): a
    sentence that Kokoro synthesises in 0.7 s took 2.3-2.9 s from the third request onward,
    and stayed at 0.7 s once opted out. Returns False where unsupported.
    """
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class PowerThrottlingState(ctypes.Structure):
        _fields_ = [
            ("Version", wintypes.ULONG),
            ("ControlMask", wintypes.ULONG),
            ("StateMask", wintypes.ULONG),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.SetProcessInformation.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
    ]
    kernel.SetProcessInformation.restype = wintypes.BOOL
    # Version 1; ControlMask EXECUTION_SPEED; StateMask 0 means "do not throttle".
    state = PowerThrottlingState(1, 0x1, 0x0)
    process_power_throttling = 4
    return bool(kernel.SetProcessInformation(
        kernel.GetCurrentProcess(), process_power_throttling,
        ctypes.byref(state), ctypes.sizeof(state),
    ))
