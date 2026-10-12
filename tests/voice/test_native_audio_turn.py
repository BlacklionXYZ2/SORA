"""Always-on listening and native audio: a heard utterance reaches the brain as audio.

Gemma 4 E2B/E4B hear audio natively, so Core attaches the owner's clip to the reply request;
brains without audio input receive only the transcript. Checked live on E4B (2026-10-08): with
the clip attached, a deliberately wrong transcript ("Spain") was answered from the audio
("France").
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest
from tests.authorization_helpers import persist_operation_grant
from tests.voice.test_sessions import FixturePlayback, FixtureStt, FixtureVad, start_request
from tests.voice.test_streamed_reply_speech import PollingTransport, SentenceTts, started_runtime

from sora.contracts.models import CapabilityOperation
from sora.contracts.voice import VoiceTranscriptDisposition
from sora.providers.turn_audio import current_turn_audio
from sora.voice import VoiceSessionCoordinator
from sora.voice.client import StreamingVoiceClient, TranscriptHypothesis
from sora.voice.listening import wav_base64


class ListeningDialogue:
    def __init__(self, audio_input: bool) -> None:
        self.audio_input = audio_input
        self.heard: list[str | None] = []

    async def respond(self, prompt: str, context: str, **_: object) -> str:
        self.heard.append(current_turn_audio())
        return "Paris."

    async def stream_reply(
        self, prompt: str, context: str, image_data_urls: tuple[str, ...] = (), *,
        source: Literal["owner", "screen"] = "owner",
    ) -> AsyncIterator[str]:
        self.heard.append(current_turn_audio())
        yield "Paris."


@pytest.mark.asyncio
@pytest.mark.parametrize("audio_input", [True, False])
async def test_a_heard_utterance_reaches_a_native_audio_brain_as_audio(
    tmp_path: Path, audio_input: bool,
) -> None:
    dialogue = ListeningDialogue(audio_input)
    instance = await started_runtime(tmp_path, dialogue)
    try:
        request = start_request()
        await persist_operation_grant(
            instance, VoiceSessionCoordinator.resource(request),
            grant_id="grant-listen", operation=CapabilityOperation.VOICE_SESSION,
        )
        client = StreamingVoiceClient(
            transport=PollingTransport(instance), vad=FixtureVad(), stt=FixtureStt(),
            tts=SentenceTts(), playback=FixturePlayback(),
        )
        await client.start(request, grant_id="grant-listen")
        clip = wav_base64(b"\x10\x00" * 16_000)
        now = datetime.now(UTC)
        result = await client.submit_utterance(
            TranscriptHypothesis(text="Sora, what is the capital of France?", confidence=0.9,
                                 final=True, audio_wav_base64=clip),
            started_at=now - timedelta(seconds=2), ended_at=now,
        )
        await client.wait_for_output()
        assert result.disposition is VoiceTranscriptDisposition.FINALIZED
        assert dialogue.heard == [clip if audio_input else None]
        assert current_turn_audio() is None  # the clip never outlives its turn
    finally:
        await instance.close()


def test_projector_audio_is_read_from_gguf_metadata(tmp_path: Path) -> None:
    import struct

    from sora.providers.turn_audio import projector_modalities

    def key(name: str, value: bool) -> bytes:
        raw = name.encode()
        return struct.pack("<Q", len(raw)) + raw + struct.pack("<I", 7) + bytes([value])

    projector = tmp_path / "mmproj.gguf"
    projector.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 2)
                          + key("clip.has_vision_encoder", True)
                          + key("clip.has_audio_encoder", True))
    assert projector_modalities(projector) == {"vision", "audio"}
    (tmp_path / "bad.gguf").write_bytes(b"nope")
    assert projector_modalities(tmp_path / "bad.gguf") == frozenset()
