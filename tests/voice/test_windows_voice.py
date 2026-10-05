"""Local Windows worker settings, lifecycle and opt-in physical/component acceptance."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.voice.client import AudioFrame
from sora.voice.settings import VoiceSettings, resolve_assets
from sora.voice.windows_audio import KokoroTts, PressToTalkVad, WhisperStt, resolve_device
from sora.voice.windows_bridge import WindowsVoiceBridge
from sora.voice.windows_worker import AudioWorker

ROOT = Path(__file__).resolve().parents[2]


def test_invalidate_closes_pipe_and_kills_owned_launcher() -> None:
    calls: list[str] = []
    process = SimpleNamespace(
        returncode=None,
        stdin=SimpleNamespace(close=lambda: calls.append("eof")),
        kill=lambda: calls.append("kill"),
    )
    bridge = WindowsVoiceBridge()
    bridge.process = process  # type: ignore[assignment]
    bridge.invalidate()
    assert calls == ["eof", "kill"] and bridge.process is None
    assert bridge.status()["message"] == "Voice stopped after settings/access changed."


@pytest.mark.asyncio
async def test_explicit_audio_close_reports_close_not_policy_change() -> None:
    bridge = WindowsVoiceBridge()
    await bridge.close()
    assert bridge.status()["state"] == "stopped"
    assert bridge.status()["message"] == "Local audio closed. The microphone is closed."
    assert not bridge.status()["running"]


@pytest.mark.asyncio
async def test_revocation_while_launching_never_initializes_the_new_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    entering, release = asyncio.Event(), asyncio.Event()
    calls: list[str] = []
    process = SimpleNamespace(
        returncode=None,
        stdin=SimpleNamespace(close=lambda: calls.append("eof")),
        kill=lambda: calls.append("kill"),
        wait=AsyncMock(return_value=0),
    )

    async def launch(*args: Any, **kwargs: Any) -> SimpleNamespace:
        entering.set()
        await release.wait()
        return process

    monkeypatch.setattr(
        "sora.voice.windows_bridge.resolve_assets", lambda settings, project: settings
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsVoiceBridge()
    bridge.configure("http://127.0.0.1:1", "test-local-token")
    task = asyncio.create_task(bridge.start(VoiceSettings(python_executable=sys.executable)))
    await entering.wait()
    bridge.invalidate()
    release.set()
    with pytest.raises(ValueError, match="cancelled"):
        await task
    assert calls == ["eof", "kill"] and bridge.process is None


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SORA_TEST_LOCAL_VOICE"), reason="opt-in speech numpy library")
async def test_silence_is_not_transcribed_as_a_hallucinated_prompt() -> None:
    model = SimpleNamespace(transcribe=lambda *args, **kwargs: pytest.fail("Silent inference"))
    stt = WhisperStt(model, 2)
    await stt.process(AudioFrame(0, datetime.now(UTC), b"\0" * 6400), utterance_ended=False)
    with pytest.raises(ValueError, match="No audible speech"):
        await stt.process(AudioFrame(1, datetime.now(UTC), b""), utterance_ended=True)


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows kernel lifetime binding")
async def test_worker_parent_handle_exits_even_with_stalled_main_thread() -> None:
    import sys

    owner = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time; time.sleep(30)"
    )
    worker = None
    try:
        env = {**os.environ, "SORA_VOICE_PARENT_PID": str(owner.pid)}
        worker = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "from sora.voice.windows_worker import watch_parent; import time; "
            "watch_parent(); print('bound', flush=True); time.sleep(30)",
            env=env,
            stdout=asyncio.subprocess.PIPE,
        )
        assert worker.stdout is not None
        assert await asyncio.wait_for(worker.stdout.readline(), 5) == b"bound\r\n"
        owner.kill()
        await asyncio.wait_for(owner.wait(), 5)
        assert await asyncio.wait_for(worker.wait(), 5) == 0
    finally:
        for process in (worker, owner):
            if process is not None and process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name != "nt", reason="Windows private control pipe lifetime")
async def test_pipe_close_exits_even_with_stalled_worker_main_thread() -> None:
    import sys

    env = {**os.environ, "SORA_VOICE_PARENT_PID": str(os.getpid()), "SORA_VOICE_CONTROL_PIPE": "1"}
    worker = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "from sora.voice.windows_worker import watch_parent; import time; "
        "watch_parent(); print('bound', flush=True); time.sleep(30)",
        env=env,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    try:
        assert worker.stdout is not None and worker.stdin is not None
        assert await asyncio.wait_for(worker.stdout.readline(), 5) == b"bound\r\n"
        worker.stdin.close()
        assert await asyncio.wait_for(worker.wait(), 5) == 0
    finally:
        if worker.returncode is None:
            worker.kill()
            await worker.wait()


def test_v5_migration_backs_up_original_and_voice_is_live(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    original = AppSettings().model_dump(mode="json")
    original["version"] = 5
    original.pop("voice")
    path.write_text(json.dumps(original), encoding="utf-8")
    settings = AppSettingsController(tmp_path, AppSettings(), path=path)
    assert settings.saved.version == 10
    assert json.loads(next(tmp_path.glob("settings.v5-*.json")).read_text()) == original
    changes = []
    settings.on_policy_change = lambda: changes.append(True)
    settings.save(
        SettingsEdit(version=6, expected_revision=0, changes={"voice.recording_limit_seconds": 4})
    )
    assert settings.active.voice.recording_limit_seconds == 4 and changes == [True]
    assert (
        AppSettingsController(
            tmp_path, AppSettings(), path=path
        ).saved.voice.recording_limit_seconds
        == 4
    )


def test_missing_assets_never_download_and_devices_do_not_silently_substitute(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="Settings"):
        resolve_assets(VoiceSettings(), tmp_path)
    sd = SimpleNamespace(
        default=SimpleNamespace(device=(-1, -1)),
        query_hostapis=lambda: [{"name": "MME"}],
        query_devices=lambda: [
            {"hostapi": 0, "name": "Fixture", "max_input_channels": 1, "max_output_channels": 0}
        ],
    )
    assert resolve_device(sd, "MME:Fixture", input_device=True) == 0
    with pytest.raises(ValueError, match="missing or ambiguous"):
        resolve_device(sd, "MME:Fixture", input_device=False)
    with pytest.raises(ValueError, match="default"):
        resolve_device(sd, "", input_device=True)


@pytest.mark.asyncio
async def test_ptt_stt_is_bounded_and_keeps_silent_pcm(tmp_path: Path) -> None:
    del tmp_path
    vad = PressToTalkVad()
    frame = AudioFrame(0, datetime.now(UTC), b"\0" * 3200)
    assert vad.process(frame).speech
    assert vad.process(AudioFrame(1, datetime.now(UTC), b"")).utterance_ended
    stt = WhisperStt(None, 2)
    assert await stt.process(frame, utterance_ended=False) is None
    assert len(stt.buffer) == 3200  # No silence removal or timestamp compression.
    with pytest.raises(ValueError, match="limit"):
        await stt.process(AudioFrame(2, frame.captured_at, b"\0" * 64000), utterance_ended=False)
    assert not stt.buffer


@pytest.mark.asyncio
async def test_recording_release_closes_microphone_before_any_transcription() -> None:
    worker = AudioWorker()
    stream = SimpleNamespace(
        abort=lambda: calls.append("abort"), close=lambda: calls.append("close")
    )
    calls: list[str] = []
    worker.stream, worker.recording = stream, True
    worker.frames = [AudioFrame(0, datetime.now(UTC), b"\0" * 3200)]
    worker.respond = AsyncMock()  # type: ignore[method-assign]
    await worker.end()
    assert calls == ["abort", "close"] and not worker.recording and worker.stream is None
    assert worker.response_task is not None
    await worker.response_task
    worker.respond.assert_awaited_once()


@pytest.mark.asyncio
async def test_local_voice_route_rejects_remote_forged_origin_and_static_off(
    tmp_path: Path,
) -> None:
    settings = AppSettingsController(tmp_path, AppSettings())
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    route = RouteHandler(runtime)
    request = HttpRequest(
        "POST", "/api/v1/voice/local", {"X-SORA-Device-ID": "device-local"}, b'{"action":"start"}'
    )
    runtime.local_voice.start = AsyncMock()  # type: ignore[method-assign]
    try:
        assert (await route.handle_request(request)).status_code == 403
        with owner_local_scope():
            assert (
                await route.handle_request(request, remote_scopes=frozenset({"conversation:write"}))
            ).status_code == 403
            settings.save(
                SettingsEdit(
                    version=6, expected_revision=0, changes={"local_companion.voice": False}
                )
            )
            assert (await route.handle_request(request)).status_code == 403
            invalid = HttpRequest("POST", request.path, {}, b'{"action":[]}')
            assert (await route.handle_request(invalid)).status_code == 400
        runtime.local_voice.start.assert_not_awaited()
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_LOCAL_VOICE"), reason="opt-in installed local voice worker"
)
async def test_real_worker_loads_models_and_is_reaped_on_policy_change(tmp_path: Path) -> None:
    settings = AppSettingsController(
        tmp_path,
        AppSettings.model_validate(
            {
                "voice": {
                    "python_executable": str(ROOT / ".local/voice-runtime/Scripts/python.exe")
                },
            }
        ),
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="voice-test-token-123456"))
    await server.start()
    api = SoraApiClient(
        f"http://127.0.0.1:{server.actual_port}", auth_token=server.config.auth_token
    )
    try:
        status, _ = await api._request("POST", "/api/v1/voice/local", {"action": "start"})
        assert status == 200
        previous = ""
        async with asyncio.timeout(20 if os.getenv("SORA_VOICE_DEBUG_STACK") else 90):
            while runtime.local_voice.state == "loading":
                if runtime.local_voice.message != previous:
                    previous = runtime.local_voice.message
                    print(f"Voice loading: {previous}", flush=True)
                await asyncio.sleep(0.1)
        print(f"Actual voice worker: {runtime.local_voice.status()}")
        assert runtime.local_voice.state == "ready"
        worker_pid = runtime.local_voice.worker_pid
        assert worker_pid is not None
        # Hold a kernel process handle before revocation so PID reuse cannot fool the check.
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, worker_pid)
        assert handle
        process = runtime.local_voice.process
        assert process is not None and process.returncode is None
        with owner_local_scope():
            settings.save(
                SettingsEdit(
                    version=6, expected_revision=0, changes={"local_companion.voice": False}
                )
            )
        assert runtime.local_voice.process is None
        await asyncio.wait_for(process.wait(), 5)
        assert process.returncode is not None
        assert runtime.local_voice.state == "stopped"
        try:
            assert await asyncio.to_thread(kernel.WaitForSingleObject, handle, 5000) == 0
        finally:
            kernel.CloseHandle(handle)
    finally:
        if runtime.local_voice.state == "loading":
            print(runtime.local_voice.diagnostics, flush=True)
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_LOCAL_VOICE"), reason="opt-in real installed STT/TTS adapters"
)
async def test_real_speech_adapters_transcribe_and_synthesize() -> None:
    import wave

    settings = resolve_assets(VoiceSettings(), ROOT)
    stt = await asyncio.to_thread(WhisperStt.load, settings)
    with wave.open(str(ROOT / ".local/p14-voice-benchmark/corpus/sapi-1.wav")) as clip:
        assert clip.getnchannels() == 1 and clip.getsampwidth() == 2
        sample_rate = clip.getframerate()
        pcm = clip.readframes(clip.getnframes())
    if sample_rate != 16000:
        import importlib

        np = importlib.import_module("numpy")
        original = np.frombuffer(pcm, dtype="<i2")
        positions = np.arange(int(len(original) * 16000 / sample_rate)) * sample_rate / 16000
        pcm = np.interp(positions, np.arange(len(original)), original).astype("<i2").tobytes()
    await stt.process(AudioFrame(0, datetime.now(UTC), pcm), utterance_ended=False)
    result = await stt.process(AudioFrame(1, datetime.now(UTC), b""), utterance_ended=True)
    assert result is not None and "project notes" in result.text.casefold()
    tts = await asyncio.to_thread(KokoroTts.load, settings)
    chunks = [
        chunk async for chunk in tts.synthesize("SORA local voice is ready.", voice_id="af_heart")
    ]
    assert chunks and all(chunk.sample_rate == 24000 for chunk in chunks)
    print(f"Actual adapters: {result.text}; {sum(len(c.pcm_s16le) for c in chunks)} PCM bytes")


@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("SORA_TEST_LOCAL_AUDIO"), reason="opt-in real microphone/speaker")
async def test_physical_microphone_capture_discard_and_local_speaker_playback() -> None:
    import importlib

    from sora.voice.windows_audio import SoundDevicePlayback

    sd = importlib.import_module("sounddevice")
    settings = resolve_assets(VoiceSettings(), ROOT)
    frames: list[bytes] = []
    microphone = sd.RawInputStream(
        samplerate=16000,
        blocksize=1600,
        channels=1,
        dtype="int16",
        device=resolve_device(sd, "", input_device=True),
        callback=lambda data, *args: frames.append(bytes(data)),
    )
    try:
        microphone.start()
        await asyncio.sleep(0.3)
    finally:
        microphone.abort()
        microphone.close()
    assert sum(len(frame) for frame in frames) >= 3200
    frames.clear()  # Never transcribe, persist or expose ambient microphone content.
    tts = await asyncio.to_thread(KokoroTts.load, settings)
    playback = SoundDevicePlayback(sd, resolve_device(sd, "", input_device=False))
    await playback.start("physical-qa", output_device_id="local-speakers")
    try:
        async for chunk in tts.synthesize("SORA local voice is ready.", voice_id="af_heart"):
            await playback.write(chunk.pcm_s16le)
        await playback.finish()
    finally:
        await playback.abort()
