"""Client-local P14.2 microphone/VAD/STT and TTS/playback adapter pipeline."""

from __future__ import annotations

import asyncio
import uuid
from collections import deque
from collections.abc import AsyncIterable, AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sora.contracts.voice import (
    VoiceConversationIntent,
    VoiceDeviceEvent,
    VoiceDeviceKind,
    VoiceDeviceState,
    VoiceInterruptionKind,
    VoiceInterruptionRequest,
    VoiceInterruptionResult,
    VoicePlaybackCommand,
    VoicePlaybackEvent,
    VoicePlaybackState,
    VoiceSessionSnapshot,
    VoiceSessionStartRequest,
    VoiceSessionStatus,
    VoiceSpeechPreview,
    VoiceTranscriptEvent,
    VoiceTranscriptKind,
    VoiceTurnResult,
)

from .intents import classify_voice_intent
from .presentation import (
    SynthesizedAudioChunk,
    VoicePresentationClock,
    VoicePresentationFrame,
    VoicePresentationResetReason,
)


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """Client-process PCM; this type is intentionally absent from public Core contracts."""

    sequence: int
    captured_at: datetime
    pcm_s16le: bytes
    sample_rate: int = 16_000
    channels: int = 1


@dataclass(frozen=True, slots=True)
class VadDecision:
    speech: bool
    utterance_ended: bool = False


@dataclass(frozen=True, slots=True)
class TranscriptHypothesis:
    text: str
    confidence: float
    final: bool
    reference_spoken_at: datetime | None = None
    # The utterance as a base64 WAV, for brains that hear audio natively (Gemma 4 E2B/E4B).
    audio_wav_base64: str | None = None


class VadAdapter(Protocol):
    def process(self, frame: AudioFrame) -> VadDecision: ...

    def reset(self) -> None: ...


class SttAdapter(Protocol):
    async def process(
        self, frame: AudioFrame, *, utterance_ended: bool
    ) -> TranscriptHypothesis | None: ...

    def reset(self) -> None: ...


class TtsAdapter(Protocol):
    def synthesize(self, text: str, *, voice_id: str) -> AsyncIterator[SynthesizedAudioChunk]: ...


class StreamingTtsAdapter(Protocol):
    """Optional: speak text that arrives sentence by sentence."""

    def synthesize_stream(
        self, texts: AsyncIterator[str], *, voice_id: str
    ) -> AsyncIterator[SynthesizedAudioChunk]: ...


type SpeechPoll = Callable[[str, str, int], Awaitable[dict[str, Any]]]
# After Core answers, how long to wait for the last sentences of a reply already being spoken.
SPEECH_SETTLE_SECONDS = 5.0


class PlaybackSink(Protocol):
    async def start(self, playback_id: str, *, output_device_id: str) -> None: ...

    async def write(self, chunk: bytes) -> None: ...

    async def finish(self) -> None: ...

    async def abort(self) -> None: ...


class VoiceLipSyncSink(Protocol):
    """Client-local timed presentation sink; never exposed as a Core/model command."""

    async def begin(self, playback_id: str, output_epoch: int, emotion: str) -> None: ...

    async def present(self, frame: VoicePresentationFrame) -> None: ...

    async def reset(
        self,
        playback_id: str | None,
        output_epoch: int | None,
        reason: VoicePresentationResetReason,
    ) -> None: ...


class _NullLipSyncSink:
    async def begin(self, playback_id: str, output_epoch: int, emotion: str) -> None:
        return None

    async def present(self, frame: VoicePresentationFrame) -> None:
        return None

    async def reset(
        self,
        playback_id: str | None,
        output_epoch: int | None,
        reason: VoicePresentationResetReason,
    ) -> None:
        return None


class VoiceCoreTransport(Protocol):
    async def start_voice_session(
        self, request: dict[str, Any], *, grant_id: str
    ) -> dict[str, Any]: ...

    async def send_voice_transcript(
        self,
        session_id: str,
        event: dict[str, Any],
        *,
        attention_grant_id: str = "",
    ) -> dict[str, Any]: ...

    async def send_voice_device_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def send_voice_playback_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def interrupt_voice_session(
        self, session_id: str, request: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def close_voice_session(self, session_id: str) -> dict[str, Any]: ...


class StreamingVoiceClient:
    """Moves semantic transcripts and playback state across Core; PCM never crosses transport."""

    def __init__(
        self,
        *,
        transport: VoiceCoreTransport,
        vad: VadAdapter,
        stt: SttAdapter,
        tts: TtsAdapter,
        playback: PlaybackSink,
        lip_sync: VoiceLipSyncSink | None = None,
        attention_grant_id: str = "",
    ) -> None:
        self.transport = transport
        self.vad = vad
        self.stt = stt
        self.tts = tts
        self.playback = playback
        self.lip_sync = lip_sync or _NullLipSyncSink()
        self.attention_grant_id = attention_grant_id
        self.request: VoiceSessionStartRequest | None = None
        self.snapshot: VoiceSessionSnapshot | None = None
        self._utterance_id: str | None = None
        self._utterance_sequence = 0
        self._speech_started_at: datetime | None = None
        self._playback_task: asyncio.Task[None] | None = None
        self._response_in_flight = False
        self._presentation = VoicePresentationClock()
        self._cancel_reset_reason = VoicePresentationResetReason.INTERRUPTED
        self._pending_speech_interruption = False
        self._spoken_playback_id: str | None = None
        self._recent_speech: deque[str] = deque(maxlen=20)

    async def start(self, request: VoiceSessionStartRequest, *, grant_id: str) -> None:
        payload = await self.transport.start_voice_session(
            request.model_dump(mode="json"), grant_id=grant_id
        )
        self.request = request
        self.snapshot = VoiceSessionSnapshot.model_validate(payload)

    async def run(self, frames: AsyncIterable[AudioFrame]) -> tuple[VoiceTurnResult, ...]:
        if self.request is None or self.snapshot is None:
            raise RuntimeError("voice client has not started")
        results: list[VoiceTurnResult] = []
        async for frame in frames:
            result = await self.process_frame(frame)
            if result is not None:
                results.append(result)
        await self.wait_for_output()
        return tuple(results)

    async def process_frame(self, frame: AudioFrame) -> VoiceTurnResult | None:
        request, snapshot = self._active()
        decision = self.vad.process(frame)
        if not decision.speech and not decision.utterance_ended:
            return None
        if self._utterance_id is None:
            if self._has_active_response():
                await self._stop_local_output(VoicePresentationResetReason.INTERRUPTED)
                self._pending_speech_interruption = True
            self._utterance_id = f"utterance-{uuid.uuid4()}"
            self._utterance_sequence = 0
            self._speech_started_at = frame.captured_at
        hypothesis = await self.stt.process(frame, utterance_ended=decision.utterance_ended)
        if hypothesis is None:
            return None
        if hypothesis.final != decision.utterance_ended:
            raise ValueError("STT finality does not match VAD utterance boundary")
        return await self._send_hypothesis(hypothesis, frame.captured_at)

    async def submit_utterance(
        self, hypothesis: TranscriptHypothesis, *, started_at: datetime, ended_at: datetime,
    ) -> VoiceTurnResult:
        """Send speech that was already found and transcribed (always-on listening).

        Speaking over an active reply interrupts it, exactly as press-to-talk does.
        """
        if not hypothesis.final:
            raise ValueError("Always-on listening submits complete utterances only")
        self._active()
        if self._utterance_id is None:
            if self._has_active_response():
                await self._stop_local_output(VoicePresentationResetReason.INTERRUPTED)
                self._pending_speech_interruption = True
            self._utterance_id = f"utterance-{uuid.uuid4()}"
            self._utterance_sequence = 0
            self._speech_started_at = started_at
        return await self._send_hypothesis(hypothesis, ended_at)

    def her_recent_words(self) -> tuple[str, ...]:
        """What she said recently, so her own voice through the speakers is not taken as the
        owner's (sora.voice.listening.Addressee)."""
        return tuple(self._recent_speech)

    async def _send_hypothesis(
        self, hypothesis: TranscriptHypothesis, captured_at: datetime,
    ) -> VoiceTurnResult:
        request, snapshot = self._active()
        utterance_id = self._utterance_id
        if utterance_id is None:
            raise RuntimeError("No utterance is open")
        if self._pending_speech_interruption:
            interruption_kind = (
                VoiceInterruptionKind.STOP_SPEAKING
                if classify_voice_intent(hypothesis.text) is VoiceConversationIntent.STOP_SPEAKING
                else VoiceInterruptionKind.BARGE_IN
            )
            await self._interrupt(interruption_kind)
            self._pending_speech_interruption = False
            request, snapshot = self._active()
        self._utterance_sequence += 1
        event = VoiceTranscriptEvent(
            event_id=f"voice-event-{uuid.uuid4()}",
            session_id=request.session_id,
            utterance_id=utterance_id,
            sequence=self._utterance_sequence,
            kind=(VoiceTranscriptKind.FINAL if hypothesis.final else VoiceTranscriptKind.PARTIAL),
            text=hypothesis.text,
            confidence=hypothesis.confidence,
            device_generation=snapshot.input_generation,
            speech_started_at=self._speech_started_at or captured_at,
            speech_ended_at=captured_at if hypothesis.final else None,
            reference_spoken_at=hypothesis.reference_spoken_at,
            captured_at=captured_at,
            audio_wav_base64=hypothesis.audio_wav_base64 if hypothesis.final else None,
        )
        follow: asyncio.Task[None] | None = None
        if hypothesis.final:
            self._reset_utterance()
            self._response_in_flight = True
            self._spoken_playback_id = None
            poll: SpeechPoll | None = getattr(self.transport, "poll_voice_speech", None)
            if poll is not None:
                # Start speaking while Core is still writing the reply.
                follow = asyncio.create_task(
                    self._follow_speech(poll, request.session_id, event.utterance_id),
                    name=f"sora-speech-{event.utterance_id}",
                )
        try:
            payload = await self.transport.send_voice_transcript(
                request.session_id,
                event.model_dump(mode="json"),
                attention_grant_id=self.attention_grant_id,
            )
        except BaseException:
            if follow is not None:
                follow.cancel()
                await asyncio.gather(follow, return_exceptions=True)
            raise
        finally:
            if hypothesis.final:
                self._response_in_flight = False
        result = VoiceTurnResult.model_validate(payload)
        self.snapshot = result.session
        if hypothesis.final:
            if follow is not None:
                try:
                    await asyncio.wait_for(asyncio.shield(follow), SPEECH_SETTLE_SECONDS)
                except TimeoutError:
                    follow.cancel()
                await asyncio.gather(follow, return_exceptions=True)
            if (
                result.playback is not None
                and result.playback.playback_id != self._spoken_playback_id
            ):
                self._start_output(result.playback)
        return result

    async def _follow_speech(self, poll: SpeechPoll, session_id: str, utterance_id: str) -> None:
        """Long-poll Core for sentences of the reply and feed them to the speaker in order."""
        sentences: asyncio.Queue[str | None] | None = None
        after = 0
        try:
            while True:
                preview = VoiceSpeechPreview.model_validate(
                    await poll(session_id, utterance_id, after)
                )
                if preview.playback is not None and sentences is None:
                    sentences = asyncio.Queue()
                    self._start_output(preview.playback, sentences=sentences)
                    self._spoken_playback_id = preview.playback.playback_id
                if sentences is not None:
                    for sentence in preview.sentences:
                        sentences.put_nowait(sentence)
                        self._recent_speech.append(sentence)
                after = preview.next_index
                if preview.finished:
                    return
        finally:
            if sentences is not None:
                sentences.put_nowait(None)

    async def barge_in(self) -> VoiceInterruptionResult:
        """Immediately silence local output and request cancellation of the active response."""

        return await self._interrupt(VoiceInterruptionKind.BARGE_IN)

    async def stop_speaking(self, *, cancel_generation: bool = False) -> VoiceInterruptionResult:
        """Silence output while preserving reasoning unless full cancellation is explicit."""

        kind = (
            VoiceInterruptionKind.CANCEL_RESPONSE
            if cancel_generation
            else VoiceInterruptionKind.STOP_SPEAKING
        )
        return await self._interrupt(kind)

    async def wait_for_output(self) -> None:
        task = self._playback_task
        if task is None:
            return
        try:
            await task
        finally:
            if self._playback_task is task:
                self._playback_task = None

    async def device_lost(self, kind: VoiceDeviceKind) -> VoiceSessionSnapshot:
        request, snapshot = self._active()
        generation, device_id = self._device_identity(kind, request, snapshot)
        event = VoiceDeviceEvent(
            event_id=f"voice-device-{uuid.uuid4()}",
            session_id=request.session_id,
            kind=kind,
            device_id=device_id,
            state=VoiceDeviceState.LOST,
            generation=generation,
            occurred_at=datetime.now(UTC),
        )
        payload = await self.transport.send_voice_device_event(
            request.session_id, event.model_dump(mode="json")
        )
        self.snapshot = VoiceSessionSnapshot.model_validate(payload)
        if kind is VoiceDeviceKind.INPUT:
            self._reset_utterance()
            self.vad.reset()
            self.stt.reset()
        else:
            await self._stop_local_output(VoicePresentationResetReason.DEVICE_LOST)
        return self.snapshot

    async def device_recovered(self, kind: VoiceDeviceKind) -> VoiceSessionSnapshot:
        request, snapshot = self._active()
        generation, device_id = self._device_identity(kind, request, snapshot)
        event = VoiceDeviceEvent(
            event_id=f"voice-device-{uuid.uuid4()}",
            session_id=request.session_id,
            kind=kind,
            device_id=device_id,
            state=VoiceDeviceState.RECOVERED,
            generation=generation + 1,
            occurred_at=datetime.now(UTC),
        )
        payload = await self.transport.send_voice_device_event(
            request.session_id, event.model_dump(mode="json")
        )
        self.snapshot = VoiceSessionSnapshot.model_validate(payload)
        return self.snapshot

    async def close(self) -> VoiceSessionSnapshot:
        request, _snapshot = self._active()
        await self._stop_local_output(
            VoicePresentationResetReason.DISCONNECTED,
            force_reset=True,
        )
        if self.snapshot is not None and self.snapshot.status is VoiceSessionStatus.CLOSED:
            return self.snapshot
        payload = await self.transport.close_voice_session(request.session_id)
        self.snapshot = VoiceSessionSnapshot.model_validate(payload)
        self._reset_utterance()
        self.vad.reset()
        self.stt.reset()
        return self.snapshot

    async def _interrupt(self, kind: VoiceInterruptionKind) -> VoiceInterruptionResult:
        request, _snapshot = self._active()
        reason = (
            VoicePresentationResetReason.PAUSED
            if kind is VoiceInterruptionKind.STOP_SPEAKING
            else VoicePresentationResetReason.INTERRUPTED
        )
        await self._stop_local_output(reason, force_reset=True)
        interruption = VoiceInterruptionRequest(
            event_id=f"voice-interruption-{uuid.uuid4()}",
            session_id=request.session_id,
            kind=kind,
            occurred_at=datetime.now(UTC),
        )
        payload = await self.transport.interrupt_voice_session(
            request.session_id, interruption.model_dump(mode="json")
        )
        result = VoiceInterruptionResult.model_validate(payload)
        self.snapshot = result.session
        return result

    def _start_output(
        self,
        command: VoicePlaybackCommand,
        *,
        sentences: asyncio.Queue[str | None] | None = None,
    ) -> None:
        if self.snapshot is None or command.output_epoch != self.snapshot.output_epoch:
            return
        if self._playback_task is not None and not self._playback_task.done():
            raise RuntimeError("voice client already has active output")
        if sentences is None:
            self._recent_speech.append(command.text)
        self._playback_task = asyncio.create_task(
            self._synthesize_and_play(command, sentences),
            name=f"sora-{command.playback_id}",
        )

    def _speech(
        self,
        command: VoicePlaybackCommand,
        sentences: asyncio.Queue[str | None] | None,
    ) -> AsyncIterator[SynthesizedAudioChunk]:
        if sentences is None:
            return self.tts.synthesize(command.text, voice_id=command.voice_id)

        async def arriving() -> AsyncIterator[str]:
            while (sentence := await sentences.get()) is not None:
                yield sentence

        stream = getattr(self.tts, "synthesize_stream", None)
        if stream is not None:
            return stream(arriving(), voice_id=command.voice_id)  # type: ignore[no-any-return]

        async def whole() -> AsyncIterator[SynthesizedAudioChunk]:
            text = " ".join([sentence async for sentence in arriving()])
            async for chunk in self.tts.synthesize(text, voice_id=command.voice_id):
                yield chunk

        return whole()

    async def _stop_local_output(
        self,
        reason: VoicePresentationResetReason,
        *,
        force_reset: bool = False,
    ) -> None:
        task = self._playback_task
        had_active_presentation = self._presentation.active
        if task is not None and not task.done():
            self._cancel_reset_reason = reason
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        elif task is not None:
            await asyncio.gather(task, return_exceptions=True)
        self._playback_task = None
        if self._presentation.active:
            await self._reset_presentation(reason)
        elif force_reset and not had_active_presentation:
            await self._reset_presentation(reason, force=True)

    def _has_active_response(self) -> bool:
        snapshot = self.snapshot
        return bool(
            self._response_in_flight
            or (self._playback_task is not None and not self._playback_task.done())
            or (
                snapshot is not None
                and (
                    snapshot.active_generation_id is not None
                    or snapshot.active_playback_id is not None
                )
            )
        )

    async def _synthesize_and_play(
        self,
        command: VoicePlaybackCommand,
        sentences: asyncio.Queue[str | None] | None = None,
    ) -> None:
        first_chunk = True
        sequence = 0
        stream = self._speech(command, sentences)
        try:
            async for chunk in stream:
                if first_chunk:
                    await self.playback.start(
                        command.playback_id,
                        output_device_id=command.output_device_id,
                    )
                    await self._playback_event(
                        command, sequence=sequence, state=VoicePlaybackState.STARTED
                    )
                    sequence += 1
                    first_chunk = False
                    self._presentation.begin(command)
                    await self.lip_sync.begin(
                        command.playback_id,
                        command.output_epoch,
                        command.emotion.value,
                    )
                frame = self._presentation.frame(command, chunk)
                await self.lip_sync.present(frame)
                await self.playback.write(chunk.pcm_s16le)
            if first_chunk:
                raise RuntimeError("TTS produced no audio")
            await self.playback.finish()
            await self._playback_event(
                command, sequence=sequence, state=VoicePlaybackState.COMPLETED
            )
            await self._reset_presentation(VoicePresentationResetReason.COMPLETED)
        except asyncio.CancelledError:
            await self.playback.abort()
            await self._reset_presentation(self._cancel_reset_reason, force=True)
            raise
        except Exception:
            await self.playback.abort()
            await self._reset_presentation(VoicePresentationResetReason.FAILED, force=True)
            await self._playback_event(command, sequence=sequence, state=VoicePlaybackState.FAILED)
            raise
        finally:
            # Stop prefetching later sentences as soon as she is interrupted.
            close = getattr(stream, "aclose", None)
            if close is not None:
                await close()

    async def _reset_presentation(
        self,
        reason: VoicePresentationResetReason,
        *,
        force: bool = False,
    ) -> None:
        identity = self._presentation.reset()
        if identity is None and not force:
            return
        playback_id, output_epoch = identity if identity is not None else (None, None)
        await self.lip_sync.reset(playback_id, output_epoch, reason)

    async def _playback_event(
        self,
        command: VoicePlaybackCommand,
        *,
        sequence: int,
        state: VoicePlaybackState,
    ) -> None:
        request, _snapshot = self._active()
        event = VoicePlaybackEvent(
            event_id=f"voice-playback-{uuid.uuid4()}",
            session_id=request.session_id,
            playback_id=command.playback_id,
            sequence=sequence,
            state=state,  # type: ignore[arg-type]
            output_device_id=command.output_device_id,
            device_generation=command.device_generation,
            occurred_at=datetime.now(UTC),
        )
        payload = await self.transport.send_voice_playback_event(
            request.session_id, event.model_dump(mode="json")
        )
        self.snapshot = VoiceSessionSnapshot.model_validate(payload)

    def _active(self) -> tuple[VoiceSessionStartRequest, VoiceSessionSnapshot]:
        if self.request is None or self.snapshot is None:
            raise RuntimeError("voice client has not started")
        return self.request, self.snapshot

    def _reset_utterance(self) -> None:
        self._utterance_id = None
        self._utterance_sequence = 0
        self._speech_started_at = None
        self._pending_speech_interruption = False

    @staticmethod
    def _device_identity(
        kind: VoiceDeviceKind,
        request: VoiceSessionStartRequest,
        snapshot: VoiceSessionSnapshot,
    ) -> tuple[int, str]:
        if kind is VoiceDeviceKind.INPUT:
            return snapshot.input_generation, request.input_device_id
        return snapshot.output_generation, request.output_device_id
