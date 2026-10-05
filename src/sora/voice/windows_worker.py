"""Core-owned press-to-talk process. JSON control/status only; PCM stays here."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import threading
import uuid
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from sora.contracts.voice import VoiceSessionStartRequest

from .client import AudioFrame, StreamingVoiceClient
from .presentation import VoicePresentationFrame, VoicePresentationResetReason
from .settings import VoiceSettings
from .windows_audio import (
    KokoroTts,
    PressToTalkVad,
    SoundDevicePlayback,
    WhisperStt,
    audio_devices,
    resolve_device,
)


def emit(**data: Any) -> None:
    # Native library messages on stdout must not corrupt this private protocol.
    print(json.dumps(data), file=sys.__stdout__, flush=True)


def watch_parent() -> None:
    """Bind to the Core kernel handle, not the Windows venv launcher parent PID."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    parent = int(os.environ["SORA_VOICE_PARENT_PID"])
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.PeekNamedPipe.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel.PeekNamedPipe.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE only.
    if not handle:
        raise OSError("Cannot bind local audio lifetime to its Core owner")
    pipe = None
    if os.getenv("SORA_VOICE_CONTROL_PIPE") == "1":
        import msvcrt

        pipe = msvcrt.get_osfhandle(sys.stdin.fileno())

    def wait() -> None:
        while True:
            result = kernel.WaitForSingleObject(handle, 250)
            if result != 258:  # WAIT_TIMEOUT: Core still alive.
                break
            if pipe is not None and not kernel.PeekNamedPipe(pipe, None, 0, None, None, None):
                # Closing Core's pipe must stop even a native DLL import/inference stall.
                result = 0
                break
        kernel.CloseHandle(handle)
        # Parent exit or handle failure: OS closes the worker's audio handles even
        # when native inference/import has stalled the asyncio thread.
        os._exit(0 if result == 0 else 1)

    threading.Thread(target=wait, name="voice-core-lifetime", daemon=True).start()


class HttpVoiceTransport:
    def __init__(self, url: str, token: str) -> None:
        self.http = httpx.AsyncClient(
            base_url=url,
            timeout=315,
            headers={
                "Authorization": f"Bearer {token}",
                "X-SORA-Device-ID": "device-local-audio",
            },
        )

    async def request(
        self, method: str, path: str, data: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        reply = await self.http.request(method, path, json=data)
        payload: dict[str, Any] = reply.json()
        if not reply.is_success:
            raise RuntimeError(
                str(payload.get("error", {}).get("message", "Core voice request failed"))
            )
        return payload

    async def start_voice_session(
        self, request: dict[str, Any], *, grant_id: str
    ) -> dict[str, Any]:
        del grant_id
        return await self.request("POST", "/api/v1/voice/sessions", request)

    async def send_voice_transcript(
        self, session_id: str, event: dict[str, Any], *, attention_grant_id: str = ""
    ) -> dict[str, Any]:
        del attention_grant_id
        emit(state="thinking", message="SORA is answering the finalized speech.")
        return await self.request("POST", f"/api/v1/voice/sessions/{session_id}/transcript", event)

    async def send_voice_device_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/voice/sessions/{session_id}/device", event)

    async def send_voice_playback_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self.request("POST", f"/api/v1/voice/sessions/{session_id}/playback", event)
        emit(
            state="speaking" if event["state"] == "started" else "ready",
            message="Speaking locally." if event["state"] == "started" else "Hold to talk.",
        )
        return result

    async def interrupt_voice_session(
        self, session_id: str, request: dict[str, Any]
    ) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/voice/sessions/{session_id}/interrupt", request)

    async def close_voice_session(self, session_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/api/v1/voice/sessions/{session_id}/close", {})


class PipeLipSyncSink:
    """Only audio-derived metadata leaves the worker; never PCM or a model action."""

    async def begin(self, playback_id: str, output_epoch: int, emotion: str) -> None:
        emit(
            presentation={
                "op": "begin",
                "playback_id": playback_id,
                "output_epoch": output_epoch,
                "emotion": emotion,
                "emitted_at": datetime.now(UTC).isoformat(),
            }
        )

    async def present(self, frame: VoicePresentationFrame) -> None:
        emit(
            presentation={
                "op": "frame",
                **asdict(frame),
                "emitted_at": datetime.now(UTC).isoformat(),
            }
        )

    async def reset(
        self,
        playback_id: str | None,
        output_epoch: int | None,
        reason: VoicePresentationResetReason,
    ) -> None:
        emit(
            presentation={
                "op": "reset",
                "playback_id": playback_id,
                "output_epoch": output_epoch,
                "reason": reason.value,
                "emitted_at": datetime.now(UTC).isoformat(),
            }
        )


class AudioWorker:
    def __init__(self) -> None:
        self.client: StreamingVoiceClient | None = None
        self.transport: HttpVoiceTransport | None = None
        self.settings = VoiceSettings()
        self.sd: Any = None
        self.input_device = -1
        self.stream: Any = None
        self.frames: list[AudioFrame] = []
        self.failed_capture = False
        self.limit_task: asyncio.Task[None] | None = None
        self.response_task: asyncio.Task[None] | None = None
        self.init_task: asyncio.Task[None] | None = None
        self.recording = False
        self.generation = 0

    async def initialize(self, config: dict[str, Any]) -> None:
        try:
            self.settings = VoiceSettings.model_validate(config["settings"])
            emit(state="loading", message="Checking local audio libraries and devices.")
            self.sd = importlib.import_module("sounddevice")
            self.input_device = resolve_device(
                self.sd, self.settings.input_device, input_device=True
            )
            output = resolve_device(self.sd, self.settings.output_device, input_device=False)
            self.sd.check_input_settings(
                device=self.input_device, channels=1, dtype="int16", samplerate=16000
            )
            self.sd.check_output_settings(
                device=output, channels=1, dtype="int16", samplerate=24000
            )
            emit(
                state="loading",
                message="Loading existing local Whisper and Kokoro assets.",
                devices=audio_devices(self.sd),
            )
            stt = await asyncio.to_thread(WhisperStt.load, self.settings)
            emit(state="loading", message="Whisper loaded; loading local Kokoro model.")
            tts = await asyncio.to_thread(KokoroTts.load, self.settings)
            self.transport = HttpVoiceTransport(config["url"], config["token"])
            self.client = StreamingVoiceClient(
                transport=self.transport,
                vad=PressToTalkVad(),
                stt=stt,
                tts=tts,
                playback=SoundDevicePlayback(self.sd, output),
                lip_sync=PipeLipSyncSink(),
            )
            request = VoiceSessionStartRequest(
                session_id=f"voice-local-{uuid.uuid4()}",
                input_device_id="local-microphone",
                output_device_id="local-speakers",
                voice_id=self.settings.voice_id,
                started_at=datetime.now(UTC),
            )
            await self.client.start(request, grant_id="")
            emit(
                state="ready",
                message="Hold to talk. Microphone is closed.",
                session_id=request.session_id,
                worker_pid=os.getpid(),
            )
        except Exception as exc:
            emit(
                state="error",
                message=f"Local voice unavailable: {exc}. Check Voice settings/runtime.",
            )

    async def begin(self) -> None:
        if self.client is None or self.client.snapshot is None:
            raise ValueError("Voice is not ready. Start voice and wait for local models to load.")
        if self.recording:
            raise ValueError("A press-to-talk recording is already active")
        self.generation += 1
        await self.client.barge_in()
        if self.response_task is not None and not self.response_task.done():
            self.response_task.cancel()
            await asyncio.gather(self.response_task, return_exceptions=True)
        self.client.stt.reset()
        self.frames.clear()
        self.failed_capture = False
        loop = asyncio.get_running_loop()

        def accept(data: bytes, captured: datetime, failed: bool) -> None:
            if not self.recording:
                return
            if failed:
                self.failed_capture = True
            if len(self.frames) < self.settings.recording_limit_seconds * 10 + 1:
                self.frames.append(AudioFrame(len(self.frames), captured, data))

        def callback(data: Any, count: int, timing: Any, status: Any) -> None:
            del timing
            captured = datetime.now(UTC) - timedelta(seconds=count / 16000)
            loop.call_soon_threadsafe(accept, bytes(data), captured, bool(status))

        self.stream = self.sd.RawInputStream(
            samplerate=16000,
            blocksize=1600,
            channels=1,
            dtype="int16",
            device=self.input_device,
            callback=callback,
        )
        self.recording = True
        try:
            self.stream.start()
        except BaseException:
            self.recording = False
            self.stream.close()
            self.stream = None
            raise
        emit(
            state="recording",
            message="Recording only while held; release to send speech.",
            microphone_open=True,
        )
        self.limit_task = asyncio.create_task(self._limit())

    async def _limit(self) -> None:
        await asyncio.sleep(self.settings.recording_limit_seconds)
        if self.recording:
            await self.end()

    def stop_capture(self) -> None:
        self.recording = False
        stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.abort()
            finally:
                stream.close()
                emit(microphone_open=False)
        else:
            emit(microphone_open=False)
        if self.limit_task is not None and self.limit_task is not asyncio.current_task():
            self.limit_task.cancel()
        self.limit_task = None

    async def end(self) -> None:
        if not self.recording:
            return
        self.stop_capture()
        frames, self.frames = self.frames, []
        if self.failed_capture or not frames:
            raise ValueError("Microphone lost frames or captured no audio. Nothing was sent.")
        generation = self.generation
        self.response_task = asyncio.create_task(self.respond(frames, generation))

    async def respond(self, frames: list[AudioFrame], generation: int) -> None:
        assert self.client is not None
        try:
            emit(state="transcribing", message="Transcribing locally. Microphone is closed.")
            for frame in frames:
                await self.client.process_frame(frame)
            result = await self.client.process_frame(
                AudioFrame(len(frames), datetime.now(UTC), b"")
            )
            if generation != self.generation:
                return
            if result is not None and result.playback is not None:
                await self.client.wait_for_output()
            if generation == self.generation:
                emit(state="ready", message="Hold to talk. Microphone is closed.")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if generation == self.generation:
                self.client.stt.reset()
                self.client.vad.reset()
                self.client._reset_utterance()
                emit(state="error", message=f"Voice turn failed: {exc}")

    async def stop(self) -> None:
        self.generation += 1
        self.stop_capture()
        self.frames.clear()
        if self.client is not None:
            await self.client.barge_in()
            self.client.stt.reset()
            self.client._reset_utterance()
        if self.response_task is not None:
            self.response_task.cancel()
            await asyncio.gather(self.response_task, return_exceptions=True)
        emit(state="ready" if self.client else "stopped", message="Stopped. Microphone is closed.")

    async def stop_output(self) -> None:
        """Silence playback without closing capture or cancelling the voice generation."""
        if self.client is None:
            raise ValueError("Start local voice first")
        await self.client.stop_speaking(cancel_generation=False)

    async def close(self) -> None:
        self.stop_capture()
        if self.client is not None:
            try:
                await asyncio.wait_for(self.stop(), 3)
                await asyncio.wait_for(self.client.close(), 3)
            except Exception:
                pass
        if self.transport is not None:
            await self.transport.http.aclose()


async def main() -> None:
    watch_parent()
    if os.getenv("SORA_VOICE_DEBUG_STACK"):
        import faulthandler

        faulthandler.dump_traceback_later(12, file=sys.stderr)
    worker = AudioWorker()
    # Third-party diagnostics belong to stderr; protocol output uses original stdout.
    sys.stdout = sys.stderr
    try:
        # Initialise native numeric/audio DLLs on the main thread, before PortAudio and
        # the background pipe reader exist. NumPy's Windows DLL initialisation can stall
        # when first imported from the concurrent model-loading thread.
        emit(state="loading", message="Importing local speech libraries; microphone closed.")
        for module in ("numpy", "faster_whisper", "kokoro_onnx", "sounddevice"):
            importlib.import_module(module)
        while True:
            line = await asyncio.to_thread(sys.stdin.readline, 16385)
            if not line:
                break
            command = json.loads(line)
            request_id = command.get("id")
            try:
                operation = command["op"]
                if operation == "init":
                    if worker.init_task is not None:
                        raise ValueError("Voice worker was already initialized")
                    worker.init_task = asyncio.create_task(worker.initialize(command))
                elif operation == "begin":
                    await worker.begin()
                elif operation == "end":
                    await worker.end()
                elif operation == "stop":
                    await worker.stop()
                elif operation == "stop_output":
                    await worker.stop_output()
                elif operation == "close":
                    break
                else:
                    raise ValueError("Unsupported local voice operation")
                emit(reply_to=request_id, ok=True)
            except Exception as exc:
                emit(reply_to=request_id, ok=False, message=str(exc))
    finally:
        await worker.close()
        # Native model loading/inference may still occupy an executor thread after EOF.
        # All PCM streams are closed above; don't keep an orphan audio process alive.
        os._exit(0)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        # Native inference can outlive a cancelled to_thread task. The owned process must
        # not wait for that executor after parent stdin closes; PCM streams are closed above.
        os._exit(0)
