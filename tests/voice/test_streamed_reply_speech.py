"""Voice replies are spoken sentence by sentence while the model is still writing them."""

from __future__ import annotations

import asyncio
import json
import struct
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

import httpx
import pytest
from tests.authorization_helpers import persist_operation_grant
from tests.voice.test_sessions import (
    ROOT,
    FixturePlayback,
    FixtureStt,
    FixtureVad,
    RuntimeVoiceTransport,
    interruption,
    open_session,
    start_request,
    transcript,
)

from sora.contracts.models import ActiveCapabilitySet, CapabilityOperation
from sora.contracts.voice import (
    VoiceInterruptionKind,
    VoiceSpeechPreview,
    VoiceTranscriptDisposition,
    VoiceTranscriptKind,
)
from sora.providers.dialogue import OpenAICompatibleDialogueProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.voice import VoiceSessionCoordinator
from sora.voice.client import AudioFrame, StreamingVoiceClient
from sora.voice.presentation import SynthesizedAudioChunk
from sora.voice.speech_stream import VOICE_REPLY_NOTE, SentenceStream


class StreamingDialogue:
    """Writes the first sentence, then waits until the test lets it finish."""

    def __init__(self) -> None:
        self.release = asyncio.Event()
        self.contexts: list[str] = []

    async def respond(
        self, prompt: str, context: str, *, active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        del prompt, active_capabilities
        self.contexts.append(context)
        return "Typed reply."

    async def stream_response(
        self, prompt: str, context: str, *, active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        yield await self.respond(prompt, context, active_capabilities=active_capabilities)

    async def stream_reply(
        self,
        prompt: str,
        context: str,
        image_data_urls: tuple[str, ...] = (),
        *,
        source: Literal["owner", "screen"] = "owner",
    ) -> AsyncIterator[str]:
        del prompt, image_data_urls, source
        self.contexts.append(context)
        for delta in ("Hi ", "there! I can", " see your "):
            yield delta
        await self.release.wait()
        for delta in ("screen. All", " good."):
            yield delta


class PollingTransport(RuntimeVoiceTransport):
    async def poll_voice_speech(
        self, session_id: str, utterance_id: str, after: int,
    ) -> dict[str, object]:
        preview = await self.runtime.wait_voice_speech(
            session_id, device_id="device-local", utterance_id=utterance_id, after=after,
        )
        return preview.model_dump(mode="json")


class SentenceTts:
    CHUNK = struct.pack("<160h", *([3_000] * 160))

    def __init__(self) -> None:
        self.pieces: list[str] = []
        self.first_piece = asyncio.Event()

    async def synthesize(self, text: str, *, voice_id: str) -> AsyncIterator[SynthesizedAudioChunk]:
        raise AssertionError(f"whole-reply synthesis was not expected: {text!r}")
        yield  # pragma: no cover

    async def synthesize_stream(
        self, texts: AsyncIterator[str], *, voice_id: str
    ) -> AsyncIterator[SynthesizedAudioChunk]:
        sequence = 0
        async for text in texts:
            self.pieces.append(text)
            self.first_piece.set()
            yield SynthesizedAudioChunk(sequence=sequence, pcm_s16le=self.CHUNK)
            sequence += 1


async def started_runtime(tmp_path: Path, dialogue: object) -> SoraRuntime:
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        dialogue_provider=dialogue,  # type: ignore[arg-type]
    )
    await instance.start()
    return instance


@pytest.mark.asyncio
async def test_first_sentence_is_spoken_before_the_reply_is_finished(tmp_path: Path) -> None:
    dialogue = StreamingDialogue()
    instance = await started_runtime(tmp_path, dialogue)
    try:
        request = start_request()
        await persist_operation_grant(
            instance, VoiceSessionCoordinator.resource(request),
            grant_id="grant-streamed", operation=CapabilityOperation.VOICE_SESSION,
        )
        tts, playback = SentenceTts(), FixturePlayback()
        client = StreamingVoiceClient(
            transport=PollingTransport(instance), vad=FixtureVad(), stt=FixtureStt(),
            tts=tts, playback=playback,
        )
        await client.start(request, grant_id="grant-streamed")

        async def microphone() -> AsyncIterator[AudioFrame]:
            now = datetime.now(UTC)
            yield AudioFrame(sequence=1, captured_at=now, pcm_s16le=b"one")
            yield AudioFrame(sequence=2, captured_at=now + timedelta(milliseconds=250),
                             pcm_s16le=b"two")

        run = asyncio.create_task(client.run(microphone()))
        await asyncio.wait_for(tts.first_piece.wait(), 5)
        # Speaking has begun while the model is still writing and nothing is committed yet.
        assert tts.pieces == ["Hi there!"]
        assert not run.done()
        assert await instance.repository.list_messages(instance.config.conversation_id) == []
        dialogue.release.set()
        results = await asyncio.wait_for(run, 5)

        final = results[-1]
        assert final.disposition is VoiceTranscriptDisposition.FINALIZED
        assert final.assistant_text == "Hi there! I can see your screen. All good."
        assert tts.pieces == ["Hi there!", "I can see your screen.", "All good."]
        assert final.playback is not None
        assert [started for started, _ in playback.started] == [final.playback.playback_id]
        assert playback.finished == 1 and playback.aborted == 0
        assert VOICE_REPLY_NOTE in dialogue.contexts[-1]
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_interrupted_reply_stops_offering_sentences(tmp_path: Path) -> None:
    dialogue = StreamingDialogue()
    instance = await started_runtime(tmp_path, dialogue)
    try:
        request = await open_session(instance)
        event = transcript(
            request, event_id="voice-event-1", utterance_id="utterance-1", sequence=1,
            text="hello", kind=VoiceTranscriptKind.FINAL,
        )
        turn = asyncio.create_task(
            instance.ingest_voice_transcript(event, device_id="device-local")
        )
        first = await asyncio.wait_for(instance.wait_voice_speech(
            request.session_id, device_id="device-local", utterance_id="utterance-1", after=0,
        ), 5)
        assert first.sentences == ("Hi there!",) and first.playback is not None
        await instance.interrupt_voice_session(
            interruption(request, event_id="stop-1", kind=VoiceInterruptionKind.STOP_SPEAKING),
            device_id="device-local",
        )
        after = await asyncio.wait_for(instance.wait_voice_speech(
            request.session_id, device_id="device-local", utterance_id="utterance-1", after=1,
        ), 5)
        assert after.finished and after.playback is None and after.sentences == ()
        dialogue.release.set()
        result = await asyncio.wait_for(turn, 5)
        assert result.playback is None  # The stopped reply is not spoken again at the end.
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_another_utterance_never_receives_this_reply(tmp_path: Path) -> None:
    dialogue = StreamingDialogue()
    instance = await started_runtime(tmp_path, dialogue)
    try:
        request = await open_session(instance)
        event = transcript(
            request, event_id="voice-event-1", utterance_id="utterance-1", sequence=1,
            text="hello", kind=VoiceTranscriptKind.FINAL,
        )
        turn = asyncio.create_task(
            instance.ingest_voice_transcript(event, device_id="device-local")
        )
        await asyncio.sleep(0.2)
        other = await instance.voice_sessions.wait_speech(
            request.session_id, device_id="device-local", utterance_id="utterance-old",
            after=0, timeout=0.2,
        )
        assert other == VoiceSpeechPreview(session_id=request.session_id, next_index=0)
        dialogue.release.set()
        await asyncio.wait_for(turn, 5)
    finally:
        await instance.close()


@pytest.mark.parametrize(
    ("deltas", "expected"),
    [
        (["Hi", " there! How", " are you?"], ["Hi there!", "How are you?"]),
        (["1. Open it\n2. Save it."], ["1. Open it", "2. Save it."]),
        (["It costs 3.5 pounds. Fine"], ["It costs 3.5 pounds.", "Fine"]),
        (['She said "hi." Then left'], ['She said "hi."', "Then left"]),
    ],
)
def test_sentence_stream(deltas: list[str], expected: list[str]) -> None:
    stream = SentenceStream()
    sentences = [sentence for delta in deltas for sentence in stream.feed(delta)]
    assert sentences + stream.flush() == expected


def sse(*events: dict[str, Any] | str) -> bytes:
    lines = [
        "data: " + (event if isinstance(event, str) else json.dumps(event)) + "\n\n"
        for event in events
    ]
    return "".join(lines).encode()


def mock_server(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response],
) -> list[dict[str, Any]]:
    bodies: list[dict[str, Any]] = []
    real = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return handler(request)

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return bodies


@pytest.mark.asyncio
async def test_provider_streams_reply_text_and_skips_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = sse(
        {"choices": [{"delta": {"reasoning_content": "Let me think."}}]},
        {"choices": [{"delta": {"content": "Hi "}}]},
        {"choices": [{"delta": {"content": "there."}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        "[DONE]",
    )
    bodies = mock_server(monkeypatch, lambda request: httpx.Response(200, content=body))
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1/v1", model="m")
    parts = [part async for part in provider.stream_reply("hi", "context")]
    assert parts == ["Hi ", "there."]
    assert bodies[0]["stream"] is True


@pytest.mark.asyncio
async def test_provider_rejects_an_empty_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    from sora.providers.dialogue import DialogueProviderError

    mock_server(monkeypatch, lambda request: httpx.Response(200, content=sse("[DONE]")))
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1/v1", model="m")
    with pytest.raises(DialogueProviderError):
        _ = [part async for part in provider.stream_reply("hi", "context")]
