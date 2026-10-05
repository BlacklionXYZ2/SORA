"""Opt-in actual local output ↔ packaged VRM mouth integration, synthetic transcript."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.voice import VoiceSessionStartRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.voice.client import AudioFrame, StreamingVoiceClient, TranscriptHypothesis
from sora.voice.settings import VoiceSettings, resolve_assets
from sora.voice.windows_audio import KokoroTts, PressToTalkVad, SoundDevicePlayback, resolve_device
from sora.voice.windows_worker import HttpVoiceTransport, PipeLipSyncSink


class SyntheticStt:
    async def process(
        self, frame: AudioFrame, *, utterance_ended: bool
    ) -> TranscriptHypothesis | None:
        return TranscriptHypothesis("Hello SORA.", 0.98, True) if utterance_ended else None

    def reset(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_UNITY_VOICE"), reason="opt-in packaged VRM and actual speaker"
)
async def test_actual_speaker_and_packaged_vrm_receive_pcm_derived_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[2]
    evidence_dir = root / ".local/w5-voice-mouth-evidence" / uuid.uuid4().hex
    evidence_dir.mkdir(parents=True)
    evidence = evidence_dir / "voice-frames.json"
    player = root / "clients/unity/Builds/Windows/SORA.exe"
    settings = AppSettingsController(
        tmp_path,
        AppSettings.model_validate(
            {
                "perception": {"paused": True},
                "local_companion": {
                    "file_read": False,
                    "desktop_observe": False,
                    "desktop_capture": False,
                    "agent_delegation": False,
                },
            }
        ),
    )
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=root / "identity"),
        provider=DeterministicProvider(),
        app_settings=settings,
    )
    await runtime.start()
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="voice-vrm-qa-token-123456"))
    process = None
    transport = None
    client = None
    try:
        await server.start()
        env = {
            **os.environ,
            "SORA_API_TOKEN": server.config.auth_token,
            "SORA_CORE_PORT": str(server.actual_port),
            "SORA_CORE_PARENT_PID": str(os.getpid()),
            "SORA_EMBODIMENT_DEVICE_ID": "device-local",
            "SORA_VOICE_EVIDENCE_PATH": str(evidence),
        }
        for key in list(env):
            if key.startswith("SORA_") and (
                "GRANT" in key
                or key == "SORA_VRM_PATH"
                or ("EVIDENCE" in key and key != "SORA_VOICE_EVIDENCE_PATH")
            ):
                env.pop(key)
        process = await asyncio.create_subprocess_exec(
            str(player), "-logFile", str(evidence_dir / "voice-player.log"), env=env
        )
        async with asyncio.timeout(45):
            while runtime.embodiment_state is None or not runtime.embodiment_state.visible:
                assert process.returncode is None
                await asyncio.sleep(0.1)
        sd = importlib.import_module("sounddevice")
        tts = await asyncio.to_thread(KokoroTts.load, resolve_assets(VoiceSettings(), root))
        transport = HttpVoiceTransport(
            f"http://127.0.0.1:{server.actual_port}", server.config.auth_token
        )
        monkeypatch.setattr(
            "sora.voice.windows_worker.emit",
            lambda **data: (
                runtime.local_voice.presentation.publish(data["presentation"])
                if "presentation" in data
                else None
            ),
        )
        client = StreamingVoiceClient(
            transport=transport,
            vad=PressToTalkVad(),
            stt=SyntheticStt(),
            tts=tts,
            playback=SoundDevicePlayback(sd, resolve_device(sd, "", input_device=False)),
            lip_sync=PipeLipSyncSink(),
        )
        await client.start(
            VoiceSessionStartRequest(
                session_id="voice-vrm-test",
                input_device_id="fixture-input",
                output_device_id="local-speakers",
                voice_id="af_heart",
                started_at=datetime.now(UTC),
            ),
            grant_id="",
        )
        await client.process_frame(AudioFrame(0, datetime.now(UTC), b"\0" * 3200))
        result = await client.process_frame(AudioFrame(1, datetime.now(UTC), b""))
        assert result is not None and result.playback is not None
        await asyncio.wait_for(client.wait_for_output(), 45)
        await asyncio.sleep(0.3)
        samples = json.loads(evidence.read_text(encoding="utf-8"))
        assert any(s["mouth_open"] > 0.02 and s["vrm_mouth_weight"] > 0.02 for s in samples)
        assert any(s["vrm_applied_weight"] > 0.02 for s in samples)
        assert samples[-1]["mouth_open"] == samples[-1]["vrm_mouth_weight"] == 0
        assert samples[-1]["vrm_applied_weight"] == 0
        assert samples[-1]["reset_reason"] == "Completed"

        async def wait_mouth(playback_id: str, reason: str | None = None) -> None:
            async with asyncio.timeout(15):
                while True:
                    try:
                        current = json.loads(evidence.read_text(encoding="utf-8"))
                        if reason is None and any(
                            s["playback_id"] == playback_id and s["vrm_applied_weight"] > 0.02
                            for s in current
                        ):
                            return
                        if (
                            reason is not None
                            and current[-1]["reset_reason"] == reason
                            and current[-1]["vrm_applied_weight"] == 0
                        ):
                            assert current[-1]["mouth_open"] == current[-1]["vrm_mouth_weight"] == 0
                            return
                    except json.JSONDecodeError:
                        pass  # Opt-in evidence can be between truncation and write.
                    await asyncio.sleep(0.05)

        for reason in ("Interrupted", "DeviceLost", "Disconnected"):
            await client.process_frame(AudioFrame(0, datetime.now(UTC), b"\0" * 3200))
            turn = await client.process_frame(AudioFrame(1, datetime.now(UTC), b""))
            assert turn is not None and turn.playback is not None
            await wait_mouth(turn.playback.playback_id)
            if reason == "Interrupted":
                await client.stop_speaking(cancel_generation=True)
            elif reason == "DeviceLost":
                from sora.contracts.voice import VoiceDeviceKind

                await client.device_lost(VoiceDeviceKind.OUTPUT)
                await client.device_recovered(VoiceDeviceKind.OUTPUT)
            else:
                await client.close()
            await wait_mouth(turn.playback.playback_id, reason)
        print(
            "Actual VRM resets: Completed, Interrupted, DeviceLost (synthetic event), Disconnected"
        )
        print(
            f"Actual VRM: {len(samples)} samples; "
            f"peak {max(s['vrm_mouth_weight'] for s in samples):.3f}; completed reset"
        )
        print(f"Evidence: {evidence_dir}")
    finally:
        try:
            if client is not None:
                await client.close()
        finally:
            if transport is not None:
                await transport.http.aclose()
            if process is not None and process.returncode is None:
                process.terminate()
                await asyncio.wait_for(process.wait(), 10)
            await server.close()
            await runtime.close()
