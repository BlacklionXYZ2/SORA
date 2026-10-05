"""P14.2 streaming voice-session and durable-turn acceptance."""

from __future__ import annotations

import asyncio
import struct
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from pydantic import ValidationError
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.attention import CursorSample, CursorSampleBatch
from sora.contracts.models import ActiveCapabilitySet, CapabilityOperation, GrantStatus, TaskStatus
from sora.contracts.voice import (
    VoiceControlStatus,
    VoiceConversationIntent,
    VoiceDeviceEvent,
    VoiceDeviceKind,
    VoiceDeviceState,
    VoiceEmotion,
    VoiceInterruptionDisposition,
    VoiceInterruptionKind,
    VoiceInterruptionRequest,
    VoicePlaybackCommand,
    VoicePlaybackEvent,
    VoicePlaybackState,
    VoiceReferenceStatus,
    VoiceSessionStartRequest,
    VoiceSessionStatus,
    VoiceTranscriptDisposition,
    VoiceTranscriptEvent,
    VoiceTranscriptKind,
    VoiceTurnResult,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.voice import VoiceSessionCoordinator
from sora.voice.client import (
    AudioFrame,
    StreamingVoiceClient,
    TranscriptHypothesis,
    VadDecision,
)
from sora.voice.presentation import (
    SynthesizedAudioChunk,
    VoicePresentationClock,
    VoicePresentationFrame,
    VoicePresentationResetReason,
    pcm_s16le_rms,
)

ROOT = Path(__file__).resolve().parents[2]


class CountingDialogueProvider:
    def __init__(self, *, delay: float = 0) -> None:
        self.calls: list[str] = []
        self.contexts: list[str] = []
        self.delay = delay

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del active_capabilities
        self.calls.append(prompt)
        self.contexts.append(context)
        if self.delay:
            await asyncio.sleep(self.delay)
        return f"SORA heard: {prompt}"

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        yield await self.respond(prompt, context, active_capabilities=active_capabilities)


class RuntimeVoiceTransport:
    def __init__(self, runtime: SoraRuntime) -> None:
        self.runtime = runtime
        self.semantic_payloads: list[dict[str, object]] = []

    async def start_voice_session(
        self, request: dict[str, object], *, grant_id: str
    ) -> dict[str, object]:
        model = VoiceSessionStartRequest.model_validate(request)
        result = await self.runtime.start_voice_session(
            model, grant_id=grant_id, device_id="device-local"
        )
        return result.model_dump(mode="json")

    async def send_voice_transcript(
        self,
        session_id: str,
        event: dict[str, object],
        *,
        attention_grant_id: str = "",
    ) -> dict[str, object]:
        assert "pcm_s16le" not in event and "audio" not in event
        self.semantic_payloads.append(event)
        model = VoiceTranscriptEvent.model_validate(event)
        assert model.session_id == session_id
        result = await self.runtime.ingest_voice_transcript(
            model,
            device_id="device-local",
            attention_grant_id=attention_grant_id,
        )
        return result.model_dump(mode="json")

    async def send_voice_device_event(
        self, session_id: str, event: dict[str, object]
    ) -> dict[str, object]:
        model = VoiceDeviceEvent.model_validate(event)
        assert model.session_id == session_id
        result = await self.runtime.update_voice_device(model, device_id="device-local")
        return result.model_dump(mode="json")

    async def send_voice_playback_event(
        self, session_id: str, event: dict[str, object]
    ) -> dict[str, object]:
        model = VoicePlaybackEvent.model_validate(event)
        assert model.session_id == session_id
        result = await self.runtime.update_voice_playback(model, device_id="device-local")
        return result.model_dump(mode="json")

    async def interrupt_voice_session(
        self, session_id: str, request: dict[str, object]
    ) -> dict[str, object]:
        model = VoiceInterruptionRequest.model_validate(request)
        assert model.session_id == session_id
        result = await self.runtime.interrupt_voice_session(model, device_id="device-local")
        return result.model_dump(mode="json")

    async def close_voice_session(self, session_id: str) -> dict[str, object]:
        result = await self.runtime.close_voice_session(session_id, device_id="device-local")
        return result.model_dump(mode="json")


class FixtureVad:
    def __init__(self) -> None:
        self.reset_count = 0

    def process(self, frame: AudioFrame) -> VadDecision:
        return VadDecision(speech=True, utterance_ended=frame.sequence == 2)

    def reset(self) -> None:
        self.reset_count += 1


class FixtureStt:
    def __init__(self) -> None:
        self.reset_count = 0

    async def process(self, frame: AudioFrame, *, utterance_ended: bool) -> TranscriptHypothesis:
        del frame
        return TranscriptHypothesis(
            text=("hello from" if not utterance_ended else "hello from the streaming fixture"),
            confidence=0.97,
            final=utterance_ended,
        )

    def reset(self) -> None:
        self.reset_count += 1


class FixtureTts:
    CHUNK_ONE = struct.pack("<160h", *([2_000] * 160))
    CHUNK_TWO = struct.pack("<160h", *([8_000] * 160))

    async def synthesize(self, text: str, *, voice_id: str) -> AsyncIterator[SynthesizedAudioChunk]:
        assert text == "SORA heard: hello from the streaming fixture"
        assert voice_id == "af_heart"
        yield SynthesizedAudioChunk(sequence=0, pcm_s16le=self.CHUNK_ONE)
        yield SynthesizedAudioChunk(sequence=1, pcm_s16le=self.CHUNK_TWO)


class FixturePlayback:
    def __init__(self) -> None:
        self.started: list[tuple[str, str]] = []
        self.chunks: list[bytes] = []
        self.finished = 0
        self.aborted = 0

    async def start(self, playback_id: str, *, output_device_id: str) -> None:
        self.started.append((playback_id, output_device_id))

    async def write(self, chunk: bytes) -> None:
        self.chunks.append(chunk)

    async def finish(self) -> None:
        self.finished += 1

    async def abort(self) -> None:
        self.aborted += 1


class GatedDialogueProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls: list[str] = []
        self.cancelled = 0
        self.completed = 0

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del context, active_capabilities
        self.calls.append(prompt)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.completed += 1
        return f"finished reasoning about: {prompt}"

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        yield await self.respond(prompt, context, active_capabilities=active_capabilities)


class BlockingTts:
    FIRST_CHUNK = struct.pack("<160h", *([4_000] * 160))
    STALE_CHUNK = struct.pack("<160h", *([12_000] * 160))

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def synthesize(self, text: str, *, voice_id: str) -> AsyncIterator[SynthesizedAudioChunk]:
        del text, voice_id
        yield SynthesizedAudioChunk(sequence=0, pcm_s16le=self.FIRST_CHUNK)
        self.started.set()
        await self.release.wait()
        yield SynthesizedAudioChunk(sequence=1, pcm_s16le=self.STALE_CHUNK)


class FixtureLipSync:
    def __init__(self) -> None:
        self.reset_count = 0
        self.begins: list[tuple[str, int, str]] = []
        self.frames: list[VoicePresentationFrame] = []
        self.resets: list[tuple[str | None, int | None, VoicePresentationResetReason]] = []

    async def begin(self, playback_id: str, output_epoch: int, emotion: str) -> None:
        self.begins.append((playback_id, output_epoch, emotion))

    async def present(self, frame: VoicePresentationFrame) -> None:
        self.frames.append(frame)

    async def reset(
        self,
        playback_id: str | None,
        output_epoch: int | None,
        reason: VoicePresentationResetReason,
    ) -> None:
        self.reset_count += 1
        self.resets.append((playback_id, output_epoch, reason))


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[tuple[SoraRuntime, CountingDialogueProvider]]:
    dialogue = CountingDialogueProvider()
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=dialogue,
    )
    await instance.start()
    try:
        yield instance, dialogue
    finally:
        await instance.close()


def start_request(now: datetime | None = None) -> VoiceSessionStartRequest:
    return VoiceSessionStartRequest(
        session_id="voice-session-1",
        input_device_id="microphone-1",
        output_device_id="speakers-1",
        started_at=now or datetime.now(UTC),
    )


async def open_session(runtime: SoraRuntime) -> VoiceSessionStartRequest:
    request = start_request()
    await persist_operation_grant(
        runtime,
        VoiceSessionCoordinator.resource(request),
        grant_id="grant-voice-session",
        operation=CapabilityOperation.VOICE_SESSION,
    )
    snapshot = await runtime.start_voice_session(
        request,
        grant_id="grant-voice-session",
        device_id="device-local",
    )
    assert snapshot.status is VoiceSessionStatus.ACTIVE
    return request


def transcript(
    request: VoiceSessionStartRequest,
    *,
    event_id: str,
    utterance_id: str,
    sequence: int,
    text: str,
    kind: VoiceTranscriptKind,
    generation: int = 1,
    speech_started_at: datetime | None = None,
    speech_ended_at: datetime | None = None,
    reference_spoken_at: datetime | None = None,
    captured_at: datetime | None = None,
) -> VoiceTranscriptEvent:
    now = captured_at or datetime.now(UTC)
    return VoiceTranscriptEvent(
        event_id=event_id,
        session_id=request.session_id,
        utterance_id=utterance_id,
        sequence=sequence,
        kind=kind,
        text=text,
        confidence=0.96,
        device_generation=generation,
        speech_started_at=speech_started_at or now - timedelta(seconds=1),
        speech_ended_at=(
            speech_ended_at or now - timedelta(milliseconds=100)
            if kind is VoiceTranscriptKind.FINAL
            else None
        ),
        reference_spoken_at=reference_spoken_at,
        captured_at=now,
    )


def interruption(
    request: VoiceSessionStartRequest,
    *,
    event_id: str,
    kind: VoiceInterruptionKind,
) -> VoiceInterruptionRequest:
    return VoiceInterruptionRequest(
        event_id=event_id,
        session_id=request.session_id,
        kind=kind,
        occurred_at=datetime.now(UTC),
    )


def database_bytes(root: Path) -> bytes:
    return b"".join(path.read_bytes() for path in (root / "data").glob("sora.db*"))


def test_public_voice_contracts_cannot_carry_audio_or_authority() -> None:
    fields = VoiceTranscriptEvent.model_fields
    assert "audio" not in fields
    assert "samples" not in fields
    assert "grant_id" not in fields
    assert "authorized_by" not in fields
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VoiceTranscriptEvent.model_validate(
            {
                "event_id": "event-raw",
                "session_id": "session-raw",
                "utterance_id": "utterance-raw",
                "sequence": 0,
                "kind": "partial",
                "text": "hello",
                "confidence": 1,
                "device_generation": 1,
                "speech_started_at": now.isoformat(),
                "captured_at": now.isoformat(),
                "audio": "base64-secret",
            }
        )


@pytest.mark.asyncio
async def test_partial_transcripts_are_volatile_and_final_turn_is_exactly_once(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, dialogue = runtime
    request = await open_session(instance)
    secret_partial = "unfinalized private hypothesis delta"
    first = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="voice-event-partial-1",
            utterance_id="utterance-1",
            sequence=1,
            text=secret_partial,
            kind=VoiceTranscriptKind.PARTIAL,
        ),
        device_id="device-local",
    )
    assert first.disposition is VoiceTranscriptDisposition.PARTIAL_ACCEPTED
    assert await instance.repository.list_messages(instance.config.conversation_id) == []
    assert secret_partial.encode() not in database_bytes(instance.config.root)

    final_event = transcript(
        request,
        event_id="voice-event-final-1",
        utterance_id="utterance-1",
        sequence=2,
        text="Please show me the latest result",
        kind=VoiceTranscriptKind.FINAL,
    )
    final, replay = await asyncio.gather(
        instance.ingest_voice_transcript(final_event, device_id="device-local"),
        instance.ingest_voice_transcript(final_event, device_id="device-local"),
    )
    assert {final.disposition, replay.disposition} == {
        VoiceTranscriptDisposition.FINALIZED,
        VoiceTranscriptDisposition.DUPLICATE,
    }
    created = final if final.disposition is VoiceTranscriptDisposition.FINALIZED else replay
    duplicate = replay if created is final else final
    assert created.playback is not None
    assert duplicate.playback is None
    assert dialogue.calls == ["Please show me the latest result"]
    messages = await instance.repository.list_messages(instance.config.conversation_id)
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Please show me the latest result"
    assert secret_partial.encode() not in database_bytes(instance.config.root)


@pytest.mark.asyncio
async def test_playback_echo_is_suppressed_without_creating_a_turn(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, dialogue = runtime
    request = await open_session(instance)
    result = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="voice-event-final-echo-source",
            utterance_id="utterance-source",
            sequence=1,
            text="hello there",
            kind=VoiceTranscriptKind.FINAL,
        ),
        device_id="device-local",
    )
    assert result.playback is not None
    await instance.update_voice_playback(
        VoicePlaybackEvent(
            event_id="playback-started-1",
            session_id=request.session_id,
            playback_id=result.playback.playback_id,
            sequence=0,
            state=VoicePlaybackState.STARTED,
            output_device_id=request.output_device_id,
            device_generation=1,
            occurred_at=datetime.now(UTC),
        ),
        device_id="device-local",
    )
    echo = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="voice-event-echo",
            utterance_id="utterance-echo",
            sequence=1,
            text=result.assistant_text or "",
            kind=VoiceTranscriptKind.FINAL,
        ),
        device_id="device-local",
    )
    assert echo.disposition is VoiceTranscriptDisposition.SUPPRESSED_ECHO
    assert echo.user_message_id is None
    assert dialogue.calls == ["hello there"]
    assert len(await instance.repository.list_messages(instance.config.conversation_id)) == 2


@pytest.mark.asyncio
async def test_device_loss_clears_partial_and_never_replays_stale_audio(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, _dialogue = runtime
    request = await open_session(instance)
    partial = transcript(
        request,
        event_id="partial-before-device-loss",
        utterance_id="utterance-device",
        sequence=1,
        text="this must be cleared",
        kind=VoiceTranscriptKind.PARTIAL,
    )
    await instance.ingest_voice_transcript(partial, device_id="device-local")
    lost_input = await instance.update_voice_device(
        VoiceDeviceEvent(
            event_id="input-lost-1",
            session_id=request.session_id,
            kind=VoiceDeviceKind.INPUT,
            device_id=request.input_device_id,
            state=VoiceDeviceState.LOST,
            generation=1,
            occurred_at=datetime.now(UTC),
        ),
        device_id="device-local",
    )
    assert lost_input.status is VoiceSessionStatus.INPUT_UNAVAILABLE
    assert lost_input.partial_text is None
    with pytest.raises(RuntimeError, match="input device is unavailable"):
        await instance.ingest_voice_transcript(
            transcript(
                request,
                event_id="final-on-lost-input",
                utterance_id="utterance-device",
                sequence=2,
                text="should not commit",
                kind=VoiceTranscriptKind.FINAL,
            ),
            device_id="device-local",
        )
    await instance.update_voice_device(
        VoiceDeviceEvent(
            event_id="input-recovered-2",
            session_id=request.session_id,
            kind=VoiceDeviceKind.INPUT,
            device_id=request.input_device_id,
            state=VoiceDeviceState.RECOVERED,
            generation=2,
            occurred_at=datetime.now(UTC),
        ),
        device_id="device-local",
    )
    result = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="final-after-input-recovery",
            utterance_id="utterance-after-recovery",
            sequence=1,
            text="input is back",
            kind=VoiceTranscriptKind.FINAL,
            generation=2,
        ),
        device_id="device-local",
    )
    assert result.playback is not None
    lost_output = await instance.update_voice_device(
        VoiceDeviceEvent(
            event_id="output-lost-1",
            session_id=request.session_id,
            kind=VoiceDeviceKind.OUTPUT,
            device_id=request.output_device_id,
            state=VoiceDeviceState.LOST,
            generation=1,
            occurred_at=datetime.now(UTC),
        ),
        device_id="device-local",
    )
    assert lost_output.status is VoiceSessionStatus.OUTPUT_UNAVAILABLE
    assert lost_output.active_playback_id is None
    await instance.update_voice_device(
        VoiceDeviceEvent(
            event_id="output-recovered-2",
            session_id=request.session_id,
            kind=VoiceDeviceKind.OUTPUT,
            device_id=request.output_device_id,
            state=VoiceDeviceState.RECOVERED,
            generation=2,
            occurred_at=datetime.now(UTC),
        ),
        device_id="device-local",
    )
    recovered = await instance.get_voice_session(request.session_id, device_id="device-local")
    assert recovered.status is VoiceSessionStatus.ACTIVE
    assert recovered.active_playback_id is None


@pytest.mark.asyncio
async def test_finalized_utterance_is_idempotent_across_runtime_restart(tmp_path: Path) -> None:
    root = tmp_path / "restart"
    first_dialogue = CountingDialogueProvider()
    first = SoraRuntime(
        RuntimeConfig(root=root, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=first_dialogue,
    )
    await first.start()
    request = await open_session(first)
    event = transcript(
        request,
        event_id="restart-final-1",
        utterance_id="restart-utterance",
        sequence=1,
        text="remember this final turn once",
        kind=VoiceTranscriptKind.FINAL,
    )
    assert (
        await first.ingest_voice_transcript(event, device_id="device-local")
    ).disposition is VoiceTranscriptDisposition.FINALIZED
    await first.close()

    second_dialogue = CountingDialogueProvider()
    second = SoraRuntime(
        RuntimeConfig(root=root, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=second_dialogue,
    )
    await second.start()
    try:
        restarted_request = request.model_copy(update={"started_at": datetime.now(UTC)})
        await second.start_voice_session(
            restarted_request,
            grant_id="grant-voice-session",
            device_id="device-local",
        )
        replay = await second.ingest_voice_transcript(
            event.model_copy(
                update={
                    "event_id": "restart-final-retry",
                    "captured_at": datetime.now(UTC),
                    "speech_started_at": datetime.now(UTC) - timedelta(seconds=1),
                    "speech_ended_at": datetime.now(UTC) - timedelta(milliseconds=100),
                }
            ),
            device_id="device-local",
        )
        assert replay.disposition is VoiceTranscriptDisposition.DUPLICATE
        assert replay.playback is None
        assert second_dialogue.calls == []
        assert len(await second.repository.list_messages(second.config.conversation_id)) == 2
    finally:
        await second.close()


@pytest.mark.asyncio
async def test_authenticated_voice_routes_join_session_transcript_and_playback(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, _dialogue = runtime
    request = start_request()
    await persist_operation_grant(
        instance,
        VoiceSessionCoordinator.resource(request),
        grant_id="grant-voice-api",
        operation=CapabilityOperation.VOICE_SESSION,
    )
    routes = RouteHandler(instance)
    headers = {"X-SORA-Device-ID": "device-local", "X-SORA-Grant-ID": "grant-voice-api"}
    opened = await routes.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/voice/sessions",
            headers,
            request.model_dump_json().encode(),
        )
    )
    assert opened.status_code == 201
    final = transcript(
        request,
        event_id="api-final-1",
        utterance_id="api-utterance-1",
        sequence=1,
        text="hello from the microphone fixture",
        kind=VoiceTranscriptKind.FINAL,
    )
    response = await routes.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/voice/sessions/{request.session_id}/transcript",
            {"X-SORA-Device-ID": "device-local"},
            final.model_dump_json().encode(),
        )
    )
    assert response.status_code == 200
    payload = response.parse_json()
    assert payload["disposition"] == "finalized"
    assert payload["playback"]["text"] == "SORA heard: hello from the microphone fixture"

    retried = await routes.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/voice/sessions",
            headers,
            request.model_dump_json().encode(),
        )
    )
    assert retried.status_code == 201
    assert retried.parse_json()["session_id"] == request.session_id


@pytest.mark.asyncio
async def test_voice_session_rechecks_revocation_before_each_update(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, _dialogue = runtime
    request = await open_session(instance)
    grant = await instance.repository.get_grant("grant-voice-session")
    assert grant is not None
    await instance.repository.save_grant(grant.model_copy(update={"status": GrantStatus.REVOKED}))
    with pytest.raises(PermissionError, match="authorization changed"):
        await instance.ingest_voice_transcript(
            transcript(
                request,
                event_id="revoked-partial",
                utterance_id="revoked-utterance",
                sequence=1,
                text="must not enter volatile session state",
                kind=VoiceTranscriptKind.PARTIAL,
            ),
            device_id="device-local",
        )


@pytest.mark.asyncio
async def test_client_pipeline_keeps_pcm_local_and_completes_tts_playback(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, dialogue = runtime
    request = start_request()
    await persist_operation_grant(
        instance,
        VoiceSessionCoordinator.resource(request),
        grant_id="grant-voice-pipeline",
        operation=CapabilityOperation.VOICE_SESSION,
    )
    transport = RuntimeVoiceTransport(instance)
    vad = FixtureVad()
    stt = FixtureStt()
    playback = FixturePlayback()
    lip_sync = FixtureLipSync()
    client = StreamingVoiceClient(
        transport=transport,
        vad=vad,
        stt=stt,
        tts=FixtureTts(),
        playback=playback,
        lip_sync=lip_sync,
    )
    await client.start(request, grant_id="grant-voice-pipeline")

    async def microphone() -> AsyncIterator[AudioFrame]:
        now = datetime.now(UTC)
        yield AudioFrame(sequence=1, captured_at=now, pcm_s16le=b"private-pcm-one")
        yield AudioFrame(
            sequence=2,
            captured_at=now + timedelta(milliseconds=250),
            pcm_s16le=b"private-pcm-two",
        )

    results = await client.run(microphone())
    assert [result.disposition for result in results] == [
        VoiceTranscriptDisposition.PARTIAL_ACCEPTED,
        VoiceTranscriptDisposition.FINALIZED,
    ]
    assert dialogue.calls == ["hello from the streaming fixture"]
    assert playback.chunks == [FixtureTts.CHUNK_ONE, FixtureTts.CHUNK_TWO]
    assert playback.finished == 1
    assert playback.aborted == 0
    assert [frame.sequence for frame in lip_sync.frames] == [0, 1]
    assert [round(frame.position_ms, 3) for frame in lip_sync.frames] == [0, 6.667]
    assert lip_sync.frames[1].mouth_open > lip_sync.frames[0].mouth_open > 0
    assert {frame.emotion for frame in lip_sync.frames} == {VoiceEmotion.WARM}
    assert lip_sync.resets[-1][2] is VoicePresentationResetReason.COMPLETED
    assert client.snapshot is not None
    assert client.snapshot.active_playback_id is None
    serialized = repr(transport.semantic_payloads).encode()
    assert b"private-pcm-one" not in serialized
    assert b"private-pcm-two" not in serialized
    assert b"pcm-chunk" not in serialized


@pytest.mark.asyncio
async def test_barge_in_cancels_generation_without_committing_or_playing(tmp_path: Path) -> None:
    dialogue = GatedDialogueProvider()
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path / "barge", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=dialogue,
    )
    await instance.start()
    pending: asyncio.Task[VoiceTurnResult] | None = None
    try:
        request = await open_session(instance)
        final = transcript(
            request,
            event_id="barge-final",
            utterance_id="barge-utterance",
            sequence=1,
            text="tell me a long answer",
            kind=VoiceTranscriptKind.FINAL,
        )
        pending = asyncio.create_task(
            instance.ingest_voice_transcript(final, device_id="device-local")
        )
        await asyncio.wait_for(dialogue.started.wait(), timeout=1)
        generating = await instance.get_voice_session(request.session_id, device_id="device-local")
        assert generating.active_generation_id is not None

        interrupt = interruption(
            request, event_id="barge-interrupt", kind=VoiceInterruptionKind.BARGE_IN
        )
        stopped = await instance.interrupt_voice_session(interrupt, device_id="device-local")
        assert stopped.disposition is VoiceInterruptionDisposition.APPLIED
        assert stopped.generation_id == generating.active_generation_id
        assert stopped.generation_cancel_requested is True
        assert stopped.output_stopped is True

        turn = await asyncio.wait_for(pending, timeout=1)
        assert turn.disposition is VoiceTranscriptDisposition.INTERRUPTED
        assert turn.playback is None
        assert dialogue.cancelled == 1
        assert dialogue.completed == 0
        assert await instance.repository.list_messages(instance.config.conversation_id) == []
        settled = await instance.get_voice_session(request.session_id, device_id="device-local")
        assert settled.active_generation_id is None
        assert settled.active_playback_id is None

        replay = await instance.interrupt_voice_session(interrupt, device_id="device-local")
        assert replay.disposition is VoiceInterruptionDisposition.DUPLICATE
        assert replay.generation_cancel_requested is True
    finally:
        dialogue.release.set()
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await instance.close()


@pytest.mark.asyncio
async def test_stop_speaking_suppresses_output_but_preserves_reasoning(tmp_path: Path) -> None:
    dialogue = GatedDialogueProvider()
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path / "stop-speaking", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=dialogue,
    )
    await instance.start()
    pending: asyncio.Task[VoiceTurnResult] | None = None
    try:
        request = await open_session(instance)
        pending = asyncio.create_task(
            instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="stop-final",
                    utterance_id="stop-utterance",
                    sequence=1,
                    text="finish thinking silently",
                    kind=VoiceTranscriptKind.FINAL,
                ),
                device_id="device-local",
            )
        )
        await asyncio.wait_for(dialogue.started.wait(), timeout=1)
        stopped = await instance.interrupt_voice_session(
            interruption(
                request,
                event_id="stop-output-only",
                kind=VoiceInterruptionKind.STOP_SPEAKING,
            ),
            device_id="device-local",
        )
        assert stopped.disposition is VoiceInterruptionDisposition.APPLIED
        assert stopped.generation_cancel_requested is False
        assert stopped.session.output_suppressed is True
        assert dialogue.cancelled == 0

        dialogue.release.set()
        turn = await asyncio.wait_for(pending, timeout=1)
        assert turn.disposition is VoiceTranscriptDisposition.FINALIZED
        assert turn.playback is None
        assert dialogue.completed == 1
        assert dialogue.cancelled == 0
        messages = await instance.repository.list_messages(instance.config.conversation_id)
        assert [message.role for message in messages] == ["user", "assistant"]
        settled = await instance.get_voice_session(request.session_id, device_id="device-local")
        assert settled.active_generation_id is None
        assert settled.active_playback_id is None
    finally:
        dialogue.release.set()
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await instance.close()


@pytest.mark.asyncio
async def test_stop_speaking_clears_queued_audio_and_api_rechecks_authority(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, _dialogue = runtime
    request = await open_session(instance)
    turn = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="queued-final",
            utterance_id="queued-utterance",
            sequence=1,
            text="queue this output",
            kind=VoiceTranscriptKind.FINAL,
        ),
        device_id="device-local",
    )
    assert turn.playback is not None
    routes = RouteHandler(instance)
    stop = interruption(
        request,
        event_id="queued-stop",
        kind=VoiceInterruptionKind.STOP_SPEAKING,
    )
    response = await routes.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/voice/sessions/{request.session_id}/interrupt",
            {"X-SORA-Device-ID": "device-local"},
            stop.model_dump_json().encode(),
        )
    )
    assert response.status_code == 200
    payload = response.parse_json()
    assert payload["playback_id"] == turn.playback.playback_id
    assert payload["generation_cancel_requested"] is False
    assert payload["session"]["active_playback_id"] is None

    grant = await instance.repository.get_grant("grant-voice-session")
    assert grant is not None
    await instance.repository.save_grant(grant.model_copy(update={"status": GrantStatus.REVOKED}))
    denied = await routes.handle_request(
        HttpRequest(
            "POST",
            f"/api/v1/voice/sessions/{request.session_id}/interrupt",
            {"X-SORA-Device-ID": "device-local"},
            interruption(
                request,
                event_id="revoked-stop",
                kind=VoiceInterruptionKind.CANCEL_RESPONSE,
            )
            .model_dump_json()
            .encode(),
        )
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_client_stop_aborts_speaker_and_resets_lip_sync_without_canceling_reasoning(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, dialogue = runtime
    request = start_request()
    await persist_operation_grant(
        instance,
        VoiceSessionCoordinator.resource(request),
        grant_id="grant-voice-client-stop",
        operation=CapabilityOperation.VOICE_SESSION,
    )
    transport = RuntimeVoiceTransport(instance)
    playback = FixturePlayback()
    tts = BlockingTts()
    lip_sync = FixtureLipSync()
    client = StreamingVoiceClient(
        transport=transport,
        vad=FixtureVad(),
        stt=FixtureStt(),
        tts=tts,
        playback=playback,
        lip_sync=lip_sync,
    )
    await client.start(request, grant_id="grant-voice-client-stop")
    result = await client.process_frame(
        AudioFrame(
            sequence=2,
            captured_at=datetime.now(UTC),
            pcm_s16le=b"client-local-final-frame",
        )
    )
    assert result is not None and result.playback is not None
    await asyncio.wait_for(tts.started.wait(), timeout=1)
    assert playback.chunks == [BlockingTts.FIRST_CHUNK]

    stopped = await client.stop_speaking()
    assert stopped.disposition is VoiceInterruptionDisposition.APPLIED
    assert stopped.generation_cancel_requested is False
    assert stopped.playback_id == result.playback.playback_id
    assert playback.aborted == 1
    assert playback.finished == 0
    assert BlockingTts.STALE_CHUNK not in playback.chunks
    assert lip_sync.reset_count >= 1
    assert lip_sync.resets[-1][2] is VoicePresentationResetReason.PAUSED
    assert dialogue.calls == ["hello from the streaming fixture"]
    assert len(await instance.repository.list_messages(instance.config.conversation_id)) == 2


@pytest.mark.asyncio
async def test_new_client_speech_automatically_barges_into_inflight_generation(
    tmp_path: Path,
) -> None:
    dialogue = GatedDialogueProvider()
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path / "client-barge", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=dialogue,
    )
    await instance.start()
    final_task: asyncio.Task[VoiceTurnResult | None] | None = None
    try:
        request = start_request()
        await persist_operation_grant(
            instance,
            VoiceSessionCoordinator.resource(request),
            grant_id="grant-client-barge",
            operation=CapabilityOperation.VOICE_SESSION,
        )
        lip_sync = FixtureLipSync()
        client = StreamingVoiceClient(
            transport=RuntimeVoiceTransport(instance),
            vad=FixtureVad(),
            stt=FixtureStt(),
            tts=FixtureTts(),
            playback=FixturePlayback(),
            lip_sync=lip_sync,
        )
        await client.start(request, grant_id="grant-client-barge")
        now = datetime.now(UTC)
        final_task = asyncio.create_task(
            client.process_frame(
                AudioFrame(sequence=2, captured_at=now, pcm_s16le=b"first-utterance")
            )
        )
        await asyncio.wait_for(dialogue.started.wait(), timeout=1)

        partial = await client.process_frame(
            AudioFrame(
                sequence=1,
                captured_at=now + timedelta(milliseconds=100),
                pcm_s16le=b"interrupting-utterance",
            )
        )
        interrupted = await asyncio.wait_for(final_task, timeout=1)
        assert interrupted is not None
        assert interrupted.disposition is VoiceTranscriptDisposition.INTERRUPTED
        assert partial is not None
        assert partial.disposition is VoiceTranscriptDisposition.PARTIAL_ACCEPTED
        assert dialogue.cancelled == 1
        assert lip_sync.resets[-1][2] is VoicePresentationResetReason.INTERRUPTED
        assert await instance.repository.list_messages(instance.config.conversation_id) == []
    finally:
        dialogue.release.set()
        if final_task is not None and not final_task.done():
            final_task.cancel()
            await asyncio.gather(final_task, return_exceptions=True)
        await instance.close()


def test_amplitude_clock_is_bounded_monotonic_and_rejects_stale_playback() -> None:
    now = datetime.now(UTC)
    command = VoicePlaybackCommand(
        playback_id="playback-clock-one",
        session_id="session-clock",
        utterance_id="utterance-clock-one",
        output_device_id="speakers-clock",
        device_generation=1,
        output_epoch=4,
        voice_id="af_heart",
        emotion=VoiceEmotion.CHEERFUL,
        text="clock fixture",
        created_at=now,
        expires_at=now + timedelta(seconds=30),
    )
    silence = SynthesizedAudioChunk(
        sequence=0,
        pcm_s16le=struct.pack("<240h", *([0] * 240)),
    )
    speech = SynthesizedAudioChunk(
        sequence=1,
        pcm_s16le=struct.pack("<240h", *([16_384] * 240)),
    )
    assert pcm_s16le_rms(silence.pcm_s16le) == 0
    assert pcm_s16le_rms(speech.pcm_s16le) == pytest.approx(0.5)

    clock = VoicePresentationClock()
    clock.begin(command)
    first = clock.frame(command, silence)
    second = clock.frame(command, speech)
    assert first.position_ms == 0
    assert first.duration_ms == 10
    assert first.mouth_open == 0
    assert second.position_ms == 10
    assert second.duration_ms == 10
    assert 0 < second.mouth_open <= 1
    assert second.emotion is VoiceEmotion.CHEERFUL

    stale = command.model_copy(
        update={"playback_id": "playback-clock-stale", "utterance_id": "utterance-stale"}
    )
    with pytest.raises(ValueError, match="stale playback identity"):
        clock.frame(stale, SynthesizedAudioChunk(sequence=2, pcm_s16le=speech.pcm_s16le))
    assert clock.reset() == (command.playback_id, command.output_epoch)
    with pytest.raises(ValueError, match="stale playback identity"):
        clock.frame(command, SynthesizedAudioChunk(sequence=2, pcm_s16le=speech.pcm_s16le))

    next_command = command.model_copy(
        update={"playback_id": "playback-clock-two", "utterance_id": "utterance-clock-two"}
    )
    clock.begin(next_command)
    with pytest.raises(ValueError, match="stale playback identity"):
        clock.frame(command, SynthesizedAudioChunk(sequence=0, pcm_s16le=speech.pcm_s16le))


def test_public_core_contracts_have_no_model_driven_mouth_frames() -> None:
    schema_text = repr(VoicePlaybackCommand.model_json_schema()).lower()
    assert "mouth_open" not in schema_text
    assert "viseme" not in schema_text
    assert "presentation_frame" not in schema_text
    assert "emotion" in VoicePlaybackCommand.model_fields
    assert "emotion" not in VoiceTranscriptEvent.model_fields


@pytest.mark.asyncio
async def test_client_disconnect_resets_active_mouth_and_discards_late_audio(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, _dialogue = runtime
    request = start_request()
    await persist_operation_grant(
        instance,
        VoiceSessionCoordinator.resource(request),
        grant_id="grant-voice-disconnect",
        operation=CapabilityOperation.VOICE_SESSION,
    )
    tts = BlockingTts()
    playback = FixturePlayback()
    lip_sync = FixtureLipSync()
    client = StreamingVoiceClient(
        transport=RuntimeVoiceTransport(instance),
        vad=FixtureVad(),
        stt=FixtureStt(),
        tts=tts,
        playback=playback,
        lip_sync=lip_sync,
    )
    await client.start(request, grant_id="grant-voice-disconnect")
    result = await client.process_frame(
        AudioFrame(
            sequence=2,
            captured_at=datetime.now(UTC),
            pcm_s16le=b"disconnect-final-frame",
        )
    )
    assert result is not None and result.playback is not None
    await asyncio.wait_for(tts.started.wait(), timeout=1)
    assert lip_sync.frames[-1].mouth_open > 0

    closed = await client.close()
    assert closed.status is VoiceSessionStatus.CLOSED
    assert playback.aborted == 1
    assert BlockingTts.STALE_CHUNK not in playback.chunks
    assert lip_sync.resets[-1] == (
        result.playback.playback_id,
        result.playback.output_epoch,
        VoicePresentationResetReason.DISCONNECTED,
    )


@pytest.mark.asyncio
async def test_delayed_transcript_resolves_cursor_at_spoken_phrase_time(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
) -> None:
    instance, dialogue = runtime
    request = await open_session(instance)
    captured_at = datetime.now(UTC)
    spoken_at = captured_at - timedelta(seconds=2)
    samples = CursorSampleBatch(
        samples=(
            CursorSample(
                timestamp=spoken_at - timedelta(milliseconds=650),
                x=100,
                y=120,
                target_element="historical-control",
                topology_revision=instance.topology_manager.revision,
            ),
            CursorSample(
                timestamp=spoken_at - timedelta(milliseconds=300),
                x=102,
                y=119,
                target_element="historical-control",
                topology_revision=instance.topology_manager.revision,
            ),
            CursorSample(
                timestamp=spoken_at,
                x=101,
                y=121,
                target_element="historical-control",
                topology_revision=instance.topology_manager.revision,
            ),
            CursorSample(
                timestamp=spoken_at + timedelta(milliseconds=500),
                x=900,
                y=700,
                target_element="completion-cursor",
                topology_revision=instance.topology_manager.revision,
            ),
            CursorSample(
                timestamp=captured_at - timedelta(milliseconds=100),
                x=902,
                y=699,
                target_element="completion-cursor",
                topology_revision=instance.topology_manager.revision,
            ),
        )
    )
    await persist_operation_grant(
        instance,
        "desktop.observe:cursor",
        grant_id="grant-spoken-cursor-samples",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    await persist_operation_grant(
        instance,
        "desktop.observe:attention",
        grant_id="grant-spoken-reference",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    await instance.ingest_cursor_samples(
        samples,
        grant_id="grant-spoken-cursor-samples",
        device_id="device-local",
    )

    result = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id="delayed-reference-final",
            utterance_id="delayed-reference",
            sequence=1,
            text="Please look at this control",
            kind=VoiceTranscriptKind.FINAL,
            speech_started_at=spoken_at - timedelta(milliseconds=700),
            speech_ended_at=spoken_at + timedelta(milliseconds=200),
            reference_spoken_at=spoken_at,
            captured_at=captured_at,
        ),
        device_id="device-local",
        attention_grant_id="grant-spoken-reference",
    )

    assert result.reference is not None
    assert result.reference.status is VoiceReferenceStatus.RESOLVED
    assert result.reference.reference_spoken_at == spoken_at
    assert result.reference.reference_id is not None
    candidate = instance.reference_resolver.get(
        result.reference.reference_id,
        owner_id=instance.config.owner_id,
        device_id="device-local",
        project_id=instance.config.project_id,
    )
    assert candidate.label == "historical-control"
    assert candidate.screen_rect is not None
    assert 99 <= candidate.screen_rect.x <= 103
    assert candidate.screen_rect.x != 902
    assert "SPOKEN_REFERENCE_V1" in dialogue.contexts[-1]
    assert "historical-control" in dialogue.contexts[-1]
    assert "completion-cursor" not in dialogue.contexts[-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("with_timing", "expected_reason"),
    (
        (False, "spoken_reference_timing_missing"),
        (True, "spoken_reference_reference_predates_buffer"),
    ),
)
async def test_missing_spoken_timing_or_buffer_history_yields_clarification(
    runtime: tuple[SoraRuntime, CountingDialogueProvider],
    with_timing: bool,
    expected_reason: str,
) -> None:
    instance, dialogue = runtime
    request = await open_session(instance)
    captured_at = datetime.now(UTC)
    spoken_at = captured_at - timedelta(seconds=2)
    await persist_operation_grant(
        instance,
        "desktop.observe:cursor",
        grant_id="grant-current-cursor-only",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    await persist_operation_grant(
        instance,
        "desktop.observe:attention",
        grant_id="grant-missing-reference-history",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    await instance.ingest_cursor_samples(
        CursorSampleBatch(
            samples=(
                CursorSample(
                    timestamp=captured_at - timedelta(milliseconds=600),
                    x=800,
                    y=600,
                    topology_revision=instance.topology_manager.revision,
                ),
                CursorSample(
                    timestamp=captured_at - timedelta(milliseconds=50),
                    x=801,
                    y=600,
                    topology_revision=instance.topology_manager.revision,
                ),
            )
        ),
        grant_id="grant-current-cursor-only",
        device_id="device-local",
    )
    result = await instance.ingest_voice_transcript(
        transcript(
            request,
            event_id=f"missing-reference-{with_timing}",
            utterance_id=f"missing-reference-{with_timing}",
            sequence=1,
            text="Please inspect this control",
            kind=VoiceTranscriptKind.FINAL,
            speech_started_at=spoken_at - timedelta(milliseconds=500),
            speech_ended_at=spoken_at + timedelta(milliseconds=200),
            reference_spoken_at=spoken_at if with_timing else None,
            captured_at=captured_at,
        ),
        device_id="device-local",
        attention_grant_id="grant-missing-reference-history",
    )
    assert result.disposition is VoiceTranscriptDisposition.FINALIZED
    assert result.reference is not None
    assert result.reference.status is VoiceReferenceStatus.CLARIFICATION_REQUIRED
    assert result.reference.reason == expected_reason
    assert result.assistant_text is not None and "Which item do you mean?" in result.assistant_text
    assert dialogue.calls == []
    assert len(await instance.repository.list_messages(instance.config.conversation_id)) == 2


@pytest.mark.asyncio
async def test_spoken_control_distinguishes_steer_cancel_new_work_and_stop_output(
    tmp_path: Path,
) -> None:
    specialist = DeterministicProvider(delay_seconds=5, supports_steer=True)
    dialogue = CountingDialogueProvider()
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity", worker_count=2),
        providers={"hermes": specialist, "deterministic": specialist},
        dialogue_provider=dialogue,
    )
    await instance.start()
    try:
        request = await open_session(instance)
        original = await instance.submit_task(
            "Research the parser behavior", explicit_provider="hermes"
        )
        await asyncio.sleep(0.05)

        async def speak(text: str, index: int) -> VoiceTurnResult:
            return await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id=f"control-event-{index}",
                    utterance_id=f"control-utterance-{index}",
                    sequence=1,
                    text=text,
                    kind=VoiceTranscriptKind.FINAL,
                ),
                device_id="device-local",
            )

        steered = await speak("Tell Hermes to focus on the regression tests", 1)
        assert steered.control is not None
        assert steered.control.intent is VoiceConversationIntent.STEER_TASK
        assert steered.control.status is VoiceControlStatus.APPLIED
        assert steered.control.task_id == original.task.task_id
        assert specialist._steering[original.run.run_id] == [
            "Tell Hermes to focus on the regression tests"
        ]

        cancelled = await speak("Cancel it", 2)
        assert cancelled.control is not None
        assert cancelled.control.intent is VoiceConversationIntent.CANCEL_TASK
        assert cancelled.control.status is VoiceControlStatus.APPLIED
        assert cancelled.control.task_id == original.task.task_id
        assert original.run.run_id in specialist._cancelled

        new_work = await speak("Start a separate task to summarize the documentation", 3)
        assert new_work.control is not None
        assert new_work.control.intent is VoiceConversationIntent.NEW_WORK
        assert new_work.control.status is VoiceControlStatus.APPLIED
        assert new_work.control.task_id not in {None, original.task.task_id}
        assert new_work.control.task_id is not None
        separate_task = await instance.runtime_repository.get_task(new_work.control.task_id)
        assert separate_task is not None
        task_messages = await instance.repository.list_messages(instance.config.conversation_id)
        separate_request = next(
            message
            for message in task_messages
            if message.message_id == separate_task.creator_message_id
        )
        assert separate_request.content == "summarize the documentation"

        stopped = await speak("Stop speaking", 4)
        assert stopped.control is not None
        assert stopped.control.intent is VoiceConversationIntent.STOP_SPEAKING
        assert stopped.control.status is VoiceControlStatus.APPLIED
        assert stopped.control.task_id is None
        assert stopped.control.output_stopped
        assert stopped.playback is None
        still_separate = await instance.runtime_repository.get_task(new_work.control.task_id)
        assert still_separate is not None
        assert still_separate.status not in {TaskStatus.CANCEL_REQUESTED, TaskStatus.CANCELLED}
        assert dialogue.calls == []
    finally:
        await instance.close()
