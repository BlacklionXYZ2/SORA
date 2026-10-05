"""Final owner-local speech uses the same companion reads, motion and commit fences."""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from tests.providers.test_local_file_and_desktop_dialogue import RecordingImageDialogue
from tests.providers.test_motion_dialogue import ChoosingProvider
from tests.runtime.test_companion_reads import Reader, call, window
from tests.voice.test_sessions import (
    CountingDialogueProvider,
    interruption,
    start_request,
    transcript,
)

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.attention import CursorSample, CursorSampleBatch
from sora.contracts.desktop import DesktopObservation
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.voice import (
    VoiceDeviceEvent,
    VoiceDeviceKind,
    VoiceDeviceState,
    VoiceInterruptionKind,
    VoicePlaybackEvent,
    VoicePlaybackState,
    VoiceReferenceStatus,
    VoiceTranscriptDisposition,
    VoiceTranscriptKind,
)
from sora.persistence.records import VoiceTurnReceipt
from sora.providers.dialogue import DialogueProviderError, DialogueTimeoutError
from sora.providers.llama_server import LlamaServerConfig
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.local_files import LocalFileViewError
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError

ROOT = Path(__file__).resolve().parents[2]


def runtime(tmp_path: Path) -> SoraRuntime:
    return SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        # These are voice tests; without a capture helper the image-on-prompt default would add
        # an honest "window image unavailable" notice to every answer.
        app_settings=AppSettingsController(
            tmp_path, AppSettings.model_validate({"perception": {"mode": "native-only"}}),
        ),
    )


async def grant_count(instance: SoraRuntime) -> int:
    return await instance.repository.database.read(
        lambda db: int(db.execute("SELECT COUNT(*) FROM grants").fetchone()[0])
    )


@pytest.mark.asyncio
async def test_voice_reads_unattached_file_outside_project_once(tmp_path: Path) -> None:
    note = tmp_path / "outside-project.txt"
    note.write_text("unattached-local-voice-evidence", encoding="utf-8")
    instance = runtime(tmp_path / "core")
    await instance.start()
    assert instance.app_settings is not None
    provider = RecordingImageDialogue()
    instance.app_settings.provider = provider
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            event = transcript(
                request,
                event_id="file",
                utterance_id="file",
                sequence=1,
                text=f"Read file {note}",
                kind=VoiceTranscriptKind.FINAL,
            )
            result = await instance.ingest_voice_transcript(event, device_id="device-local")
            assert result.disposition is VoiceTranscriptDisposition.FINALIZED
            assert result.playback is not None
            assert "unattached-local-voice-evidence" in provider.contexts[-1]
            repeated = await instance.ingest_voice_transcript(event, device_id="device-local")
            assert repeated.disposition is VoiceTranscriptDisposition.DUPLICATE
            assert repeated.playback is None
            assert len(provider.contexts) == 1
            messages = await instance.repository.list_messages(instance.config.conversation_id)
            assert len(messages) == 2
            assert "unattached-local-voice-evidence" not in repr(messages)
            assert messages[0].provenance == "finalized local voice transcript"
            assert await grant_count(instance) == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_started_voice_playback_can_finish_after_admission_ttl_and_status_is_shared(
    tmp_path: Path,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            result = await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="playback",
                    utterance_id="playback",
                    sequence=1,
                    text="Hello SORA",
                    kind=VoiceTranscriptKind.FINAL,
                ),
                device_id="device-local",
            )
            assert result.playback is not None
            assert instance.companion_status()["state"] == "thinking"
            started = VoicePlaybackEvent(
                event_id="started",
                session_id=request.session_id,
                playback_id=result.playback.playback_id,
                sequence=0,
                state=VoicePlaybackState.STARTED,
                output_device_id=request.output_device_id,
                device_generation=1,
                occurred_at=datetime.now(UTC),
            )
            await instance.update_voice_playback(started, device_id="device-local")
            assert instance.companion_status()["state"] == "talking"
            later = result.playback.expires_at + timedelta(seconds=1)
            completed = started.model_copy(
                update={
                    "event_id": "completed",
                    "sequence": 1,
                    "state": VoicePlaybackState.COMPLETED,
                    "occurred_at": later,
                }
            )
            instance.voice_sessions.playback(completed, device_id="device-local", now=later)
            assert instance.companion_status()["state"] == "idle"
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_voice_uses_native_read_loop_and_static_disabled_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])
    instance = runtime(tmp_path)
    instance.windows_bridge = AsyncMock()
    instance.windows_bridge.observe.return_value = DesktopObservation(
        status="ok", nodes=(window(),)
    )
    await instance.start()
    assert instance.app_settings is not None
    reader = Reader([call("list_windows"), call("finish")])
    instance.app_settings.provider = reader
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            result = await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="native",
                    utterance_id="native",
                    sequence=1,
                    text="Which windows are open?",
                    kind=VoiceTranscriptKind.FINAL,
                ),
                device_id="device-local",
            )
            assert result.disposition is VoiceTranscriptDisposition.FINALIZED
            assert "Fixture" in reader.observations[-1]
            assert "Read evidence:" in (result.assistant_text or "")
            assert reader.screen.await_count == 0
            assert (
                len(await instance.repository.list_messages(instance.config.conversation_id)) == 2
            )
            assert await grant_count(instance) == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_local_spoken_reference_uses_static_access_without_attention_grant(
    tmp_path: Path,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    provider = CountingDialogueProvider()
    instance.app_settings.provider = provider
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            now = datetime.now(UTC)
            spoken = now - timedelta(milliseconds=300)
            await instance.ingest_cursor_samples(
                CursorSampleBatch(
                    samples=(
                        CursorSample(
                            timestamp=spoken - timedelta(milliseconds=650),
                            x=100,
                            y=120,
                            target_element="spoken-control",
                            topology_revision=instance.topology_manager.revision,
                        ),
                        CursorSample(
                            timestamp=spoken,
                            x=100,
                            y=120,
                            target_element="spoken-control",
                            topology_revision=instance.topology_manager.revision,
                        ),
                    )
                ),
                grant_id="",
                device_id="device-local",
            )
            result = await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="reference",
                    utterance_id="reference",
                    sequence=1,
                    text="Explain this control",
                    kind=VoiceTranscriptKind.FINAL,
                    reference_spoken_at=spoken,
                    captured_at=now,
                ),
                device_id="device-local",
            )
            assert result.reference is not None
            assert result.reference.status is VoiceReferenceStatus.RESOLVED
            assert "SPOKEN_REFERENCE_V1" in provider.contexts[-1]
            assert "spoken-control" in provider.contexts[-1]
            assert await grant_count(instance) == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["wave", "walk"])
async def test_voice_motion_shares_dispatch_and_walk_uses_spoken_time(
    tmp_path: Path,
    mode: str,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    instance.app_settings.provider = ChoosingProvider(mode)  # type: ignore[arg-type]
    instance.local_avatar = AsyncMock()
    instance.local_avatar.running = True
    instance.update_embodiment_topology(
        (
            MonitorDescriptor(
                id="fixture",
                rect=ScreenRect(x=0, y=0, width=1200, height=800),
                primary=True,
            ),
        )
    )
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            now = datetime.now(UTC)
            spoken = now - timedelta(milliseconds=200)
            instance.attention_tracker.append_cursor_batch(
                CursorSampleBatch(
                    samples=(
                        CursorSample(
                            timestamp=spoken,
                            x=100,
                            y=120,
                            topology_revision=instance.topology_manager.revision,
                        ),
                        CursorSample(
                            timestamp=now,
                            x=900,
                            y=700,
                            topology_revision=instance.topology_manager.revision,
                        ),
                    )
                )
            )
            result = await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="motion",
                    utterance_id="motion",
                    sequence=1,
                    text=f"Please {mode}",
                    kind=VoiceTranscriptKind.FINAL,
                    speech_ended_at=spoken,
                    captured_at=now,
                ),
                device_id="device-local",
            )
            assert "confirms dispatch" in (result.assistant_text or "")
            if mode == "walk":
                instance.local_avatar.walk_to.assert_awaited_once_with(100, 120)
            else:
                instance.local_avatar.present.assert_awaited_once()
            assert (
                len(await instance.repository.list_messages(instance.config.conversation_id)) == 2
            )
    finally:
        await instance.close()


class StubbornVoice(CountingDialogueProvider):
    def __init__(self) -> None:
        super().__init__()
        self.entered = asyncio.Event()

    async def respond(self, prompt: str, context: str, **kwargs: object) -> str:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            return "late response"
        raise AssertionError("Unreachable fixture release")


@pytest.mark.asyncio
@pytest.mark.parametrize("cause", ["barge", "settings"])
async def test_voice_late_provider_reply_is_rejected_after_barge_or_revoke(
    tmp_path: Path,
    cause: str,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    provider = StubbornVoice()
    instance.app_settings.provider = provider
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            pending = asyncio.create_task(
                instance.ingest_voice_transcript(
                    transcript(
                        request,
                        event_id="stop",
                        utterance_id="stop",
                        sequence=1,
                        text="Give a long response",
                        kind=VoiceTranscriptKind.FINAL,
                    ),
                    device_id="device-local",
                )
            )
            await asyncio.wait_for(provider.entered.wait(), timeout=2)
            if cause == "barge":
                await instance.interrupt_voice_session(
                    interruption(
                        request,
                        event_id="interrupt",
                        kind=VoiceInterruptionKind.BARGE_IN,
                    ),
                    device_id="device-local",
                )
            else:
                instance.app_settings.save(
                    SettingsEdit(
                        version=5, expected_revision=0, changes={"local_companion.voice": False}
                    )
                )
            result = await asyncio.wait_for(pending, timeout=2)
            assert result.disposition is VoiceTranscriptDisposition.INTERRUPTED
            assert result.playback is None
            assert not await instance.repository.list_messages(instance.config.conversation_id)
            assert instance.dialogue_turns.count == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_voice_and_file_disable_are_enforced_without_grants(tmp_path: Path) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    try:
        with owner_local_scope():
            instance.app_settings.save(
                SettingsEdit(
                    version=5, expected_revision=0, changes={"local_companion.file_read": False}
                )
            )
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            with pytest.raises(LocalFileViewError, match="Settings"):
                await instance.ingest_voice_transcript(
                    transcript(
                        request,
                        event_id="file-off",
                        utterance_id="file-off",
                        sequence=1,
                        text=f"Read file {tmp_path / 'not-needed.txt'}",
                        kind=VoiceTranscriptKind.FINAL,
                    ),
                    device_id="device-local",
                )
            assert not await instance.repository.list_messages(instance.config.conversation_id)
            instance.app_settings.save(
                SettingsEdit(
                    version=5, expected_revision=1, changes={"local_companion.voice": False}
                )
            )
            with pytest.raises(OperationAuthorizationError, match="Settings"):
                await instance.start_voice_session(
                    start_request(), grant_id="", device_id="device-local"
                )
            assert await grant_count(instance) == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_voice_timeout_rejects_provider_suppressing_deadline(tmp_path: Path) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    instance.app_settings.provider = StubbornVoice()
    instance.app_settings.active = instance.app_settings.active.model_copy(
        update={
            "dialogue": instance.app_settings.active.dialogue.model_copy(
                update={"timeout_seconds": 1}
            ),
        }
    )
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            with pytest.raises(DialogueTimeoutError):
                await instance.ingest_voice_transcript(
                    transcript(
                        request,
                        event_id="timeout",
                        utterance_id="timeout",
                        sequence=1,
                        text="Long answer",
                        kind=VoiceTranscriptKind.FINAL,
                    ),
                    device_id="device-local",
                )
            assert not await instance.repository.list_messages(instance.config.conversation_id)
            assert instance.dialogue_turns.count == 0
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_slow_voice_response_has_fresh_playback_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    after = datetime.now(UTC) + timedelta(seconds=45)

    class AfterResponseClock:
        @staticmethod
        def now(*args: object) -> datetime:
            return after

    class SlowClockDialogue(CountingDialogueProvider):
        async def respond(self, prompt: str, context: str, **kwargs: object) -> str:
            monkeypatch.setattr("sora.voice.sessions.datetime", AfterResponseClock)
            return "The answer after a long generation"

    instance.app_settings.provider = SlowClockDialogue()
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            result = await instance.ingest_voice_transcript(
                transcript(
                    request,
                    event_id="slow",
                    utterance_id="slow",
                    sequence=1,
                    text="Take time to answer",
                    kind=VoiceTranscriptKind.FINAL,
                ),
                device_id="device-local",
            )
            assert result.playback is not None
            assert result.playback.created_at == after
            assert result.playback.expires_at == after + timedelta(seconds=30)
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_output_recovery_during_generation_does_not_replay_answer(tmp_path: Path) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    assert instance.app_settings is not None
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingDialogue(CountingDialogueProvider):
        async def respond(self, prompt: str, context: str, **kwargs: object) -> str:
            entered.set()
            await release.wait()
            return "Answer across device loss"

    instance.app_settings.provider = WaitingDialogue()
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            pending = asyncio.create_task(
                instance.ingest_voice_transcript(
                    transcript(
                        request,
                        event_id="device-loss",
                        utterance_id="device-loss",
                        sequence=1,
                        text="Hello",
                        kind=VoiceTranscriptKind.FINAL,
                    ),
                    device_id="device-local",
                )
            )
            await asyncio.wait_for(entered.wait(), 2)
            for state, generation in ((VoiceDeviceState.LOST, 1), (VoiceDeviceState.RECOVERED, 2)):
                await instance.update_voice_device(
                    VoiceDeviceEvent(
                        event_id=state.value,
                        session_id=request.session_id,
                        kind=VoiceDeviceKind.OUTPUT,
                        device_id=request.output_device_id,
                        state=state,
                        generation=generation,
                        occurred_at=datetime.now(UTC),
                    ),
                    device_id="device-local",
                )
            release.set()
            result = await asyncio.wait_for(pending, 2)
            assert result.disposition is VoiceTranscriptDisposition.FINALIZED
            assert result.assistant_text == "Answer across device loss"
            assert result.playback is None
            assert (
                len(await instance.repository.list_messages(instance.config.conversation_id)) == 2
            )
    finally:
        release.set()
        await instance.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status,code",
    [
        (LocalFileViewError("Disabled in Settings"), 422, "LOCAL_FILE_UNAVAILABLE"),
        (DialogueTimeoutError("Timed out"), 503, "DIALOGUE_TIMEOUT"),
        (DialogueProviderError("Model failed"), 503, "DIALOGUE_UNAVAILABLE"),
    ],
)
async def test_voice_api_exposes_shared_orchestrator_errors(
    tmp_path: Path,
    failure: Exception,
    status: int,
    code: str,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    try:
        request = start_request()
        event = transcript(
            request,
            event_id="error",
            utterance_id="error",
            sequence=1,
            text="Read notes",
            kind=VoiceTranscriptKind.FINAL,
        )
        instance.ingest_voice_transcript = AsyncMock(side_effect=failure)  # type: ignore[method-assign]
        with owner_local_scope():
            result = await RouteHandler(instance).handle_request(
                HttpRequest(
                    "POST",
                    f"/api/v1/voice/sessions/{request.session_id}/transcript",
                    {"X-SORA-Device-ID": "device-local"},
                    event.model_dump_json().encode(),
                )
            )
        assert result.status_code == status
        assert result.parse_json()["error"]["code"] == code
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_voice_interruption_at_commit_keeps_one_receipt_and_suppresses_audio(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    instance = runtime(tmp_path)
    await instance.start()
    entered, release = asyncio.Event(), asyncio.Event()
    append = instance.repository.append_voice_turn_once

    async def delayed_commit(**kwargs: Any) -> VoiceTurnReceipt:
        entered.set()
        await release.wait()
        return await append(**kwargs)

    monkeypatch.setattr(instance.repository, "append_voice_turn_once", delayed_commit)
    try:
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            event = transcript(
                request,
                event_id="committing",
                utterance_id="committing",
                sequence=1,
                text="Hello",
                kind=VoiceTranscriptKind.FINAL,
            )
            pending = asyncio.create_task(
                instance.ingest_voice_transcript(event, device_id="device-local")
            )
            await asyncio.wait_for(entered.wait(), 2)
            stopping = asyncio.create_task(
                instance.interrupt_voice_session(
                    interruption(
                        request, event_id="stop-commit", kind=VoiceInterruptionKind.BARGE_IN
                    ),
                    device_id="device-local",
                )
            )
            await asyncio.sleep(0.05)
            assert not pending.done()
            release.set()
            await asyncio.wait_for(stopping, 2)
            result = await asyncio.wait_for(pending, 2)
            assert result.disposition is VoiceTranscriptDisposition.FINALIZED
            assert result.playback is None
            assert (
                len(await instance.repository.list_messages(instance.config.conversation_id)) == 2
            )
            repeated = await instance.ingest_voice_transcript(event, device_id="device-local")
            assert repeated.disposition is VoiceTranscriptDisposition.DUPLICATE
            assert repeated.playback is None
    finally:
        release.set()
        await instance.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_VOICE_MODEL_CONFIG"),
    reason="opt-in actual local-model voice read orchestration",
)
async def test_voice_local_model_discovers_and_reads_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real model + Core transcript/receipt path; not physical mic/speaker evidence."""
    config = LlamaServerConfig.load(Path(os.environ["SORA_TEST_VOICE_MODEL_CONFIG"]))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    desktop = tmp_path / "owned-desktop"
    desktop.mkdir()
    (desktop / "project-notes.txt").write_text(
        "Latest result: VOICE PARITY CHECK PASSED. No desktop effects were requested.",
        encoding="utf-8",
    )
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [str(desktop)])
    settings = AppSettingsController(
        tmp_path / "core",
        AppSettings.model_validate(
            {
                "dialogue": {"backend": "managed-llama"},
                "llama": {**config.model_dump(), "port": port},
                "perception": {"window_context": False},
                "local_companion": {
                    "desktop_observe": False,
                    "desktop_capture": False,
                    "avatar_control": False,
                },
            }
        ),
    )
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    try:
        await settings.start()
        assert settings.model_state == "ready"
        await instance.start()
        with owner_local_scope():
            request = start_request()
            await instance.start_voice_session(request, grant_id="", device_id="device-local")
            event = transcript(
                request,
                event_id="live-read",
                utterance_id="live-read",
                sequence=1,
                text="Sora, please open the project notes and show me the latest result",
                kind=VoiceTranscriptKind.FINAL,
            )
            result = await instance.ingest_voice_transcript(event, device_id="device-local")
            print(f"Actual local-model voice transcript answer: {result.assistant_text}")
            assert result.disposition is VoiceTranscriptDisposition.FINALIZED
            assert result.playback is not None
            assert "VOICE PARITY CHECK PASSED" in (result.assistant_text or "").upper()
            assert "Read evidence:" in (result.assistant_text or "")
            assert await grant_count(instance) == 0
            repeated = await instance.ingest_voice_transcript(event, device_id="device-local")
            assert repeated.disposition is VoiceTranscriptDisposition.DUPLICATE
            assert repeated.playback is None
            assert (
                len(await instance.repository.list_messages(instance.config.conversation_id)) == 2
            )
    finally:
        await instance.close()
