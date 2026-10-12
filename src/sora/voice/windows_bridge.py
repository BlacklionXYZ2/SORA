"""Bounded Core-owned lifetime and private control pipe for the Windows audio worker."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sora import helper_processes

from .relay import LocalPresentationRelay
from .settings import VoiceSettings, resolve_assets


class WindowsVoiceBridge:
    def __init__(self) -> None:
        self.url = ""
        self.token = ""
        self.process: asyncio.subprocess.Process | None = None
        self.reader: asyncio.Task[None] | None = None
        self.stderr: asyncio.Task[None] | None = None
        self.pending: dict[str, asyncio.Future[None]] = {}
        self.state = "stopped"
        self.message = "Start local voice. The microphone is closed."
        self.devices: list[dict[str, Any]] = []
        self.session_id: str | None = None
        self.worker_pid: int | None = None
        self.lock = asyncio.Lock()
        self.diagnostics = ""
        self.microphone_open: bool | None = False
        # Always-on listening: speech is being heard right now (not yet a turn).
        self.hearing = False
        self.listening = False  # always-on listening is active
        self.lifecycle_epoch = 0
        self.presentation = LocalPresentationRelay()
        # Names the speech recogniser should expect (sora.voice.vocabulary); Core sets this.
        self.vocabulary: Callable[[], tuple[str, ...]] = tuple

    def configure(self, url: str, token: str) -> None:
        self.url, self.token = url, token

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "message": self.message,
            "devices": self.devices,
            "running": self.process is not None and self.process.returncode is None,
            "microphone_open": self.microphone_open,
            "hearing": self.hearing,
            "listening": self.listening,
        }

    async def start(self, settings: VoiceSettings) -> dict[str, Any]:
        async with self.lock:
            if (
                self.process is not None
                and self.process.returncode is None
                and self.state != "error"
            ):
                return self.status()
            await self._close()
            epoch = self.lifecycle_epoch
            if not self.url or not self.token:
                raise ValueError("Local voice requires the running authenticated Core API")
            project = Path(__file__).resolve().parents[3]
            resolved = resolve_assets(settings, project)
            dedicated = project / ".local/voice-runtime/Scripts/python.exe"
            python = settings.python_executable or (
                str(dedicated) if dedicated.is_file() else sys.executable
            )
            executable = Path(python)
            if (
                not executable.is_absolute()
                or not executable.is_file()
                or python.startswith(("\\\\", "//"))
            ):
                raise ValueError("Voice Python interpreter must be an existing absolute local file")
            env = dict(os.environ)
            env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
            env["PYTHONUNBUFFERED"] = "1"
            env["SORA_VOICE_PARENT_PID"] = str(os.getpid())
            env["SORA_VOICE_CONTROL_PIPE"] = "1"
            kwargs: dict[str, Any] = {}
            if os.name == "nt":
                kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW; no interactive console.
            process = await asyncio.create_subprocess_exec(
                python,
                "-m",
                "sora.voice.windows_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                **kwargs,
            )
            helper_processes.record("voice", getattr(process, "pid", None))
            if epoch != self.lifecycle_epoch:
                if process.stdin is not None:
                    process.stdin.close()
                if process.returncode is None:
                    process.kill()
                await process.wait()
                raise ValueError("Voice startup cancelled after settings/access changed")
            self.process = process
            self.state, self.message = "loading", "Loading local speech runtime; microphone closed."
            self.microphone_open = False
            self.session_id = None
            self.worker_pid = None
            process = self.process
            self.reader = asyncio.create_task(self._read(process))
            self.stderr = asyncio.create_task(self._drain(process))
            assert process.stdin is not None
            process.stdin.write(
                (
                    json.dumps(
                        {
                            "op": "init",
                            "settings": resolved.model_dump(),
                            "url": self.url,
                            "token": self.token,
                            "vocabulary": list(self.vocabulary()),
                        }
                    )
                    + "\n"
                ).encode()
            )
            await process.stdin.drain()
            return self.status()

    async def _read(self, process: asyncio.subprocess.Process) -> None:
        assert process.stdout is not None
        try:
            while line := await process.stdout.readline():
                data = json.loads(line)
                if self.process is not process:
                    continue
                if isinstance(data.get("microphone_open"), bool):
                    self.microphone_open = data["microphone_open"]
                if isinstance(data.get("hearing"), bool):
                    self.hearing = data["hearing"]
                if isinstance(data.get("listening"), bool):
                    self.listening = data["listening"]
                if isinstance(data.get("presentation"), dict):
                    self.presentation.publish(data["presentation"])
                reply = self.pending.pop(str(data.get("reply_to")), None)
                if reply is not None and not reply.done():
                    if data.get("ok"):
                        reply.set_result(None)
                    else:
                        reply.set_exception(
                            ValueError(str(data.get("message", "Voice operation failed")))
                        )
                if self.process is not process:
                    continue
                if data.get("state") in {
                    "loading",
                    "ready",
                    "listening",
                    "recording",
                    "transcribing",
                    "thinking",
                    "speaking",
                    "error",
                    "stopped",
                }:
                    self.state = data["state"]
                    self.message = str(data.get("message", ""))[:1000]
                if isinstance(data.get("devices"), list):
                    self.devices = data["devices"][:128]
                if isinstance(data.get("session_id"), str):
                    self.session_id = data["session_id"]
                if isinstance(data.get("worker_pid"), int):
                    self.worker_pid = data["worker_pid"]
        except (ValueError, asyncio.LimitOverrunError):
            if process.returncode is None:
                process.kill()
        finally:
            await process.wait()
            if self.process is process:
                self.microphone_open = False
                self.hearing = False
                self.listening = False
                self.presentation.reset()
                self.state = "error"
                self.message = (
                    "Local voice worker exited. Check Voice settings and installed speech runtime."
                )
                self._fail_pending()

    async def _drain(self, process: asyncio.subprocess.Process) -> None:
        assert process.stderr is not None
        while chunk := await process.stderr.read(4096):
            # Private bounded diagnostics for support; never persisted or exposed by projections.
            self.diagnostics = (self.diagnostics + chunk.decode(errors="replace"))[-16384:]
            self.diagnostics = self.diagnostics.replace(self.token, "[redacted]")

    async def command(self, operation: str) -> dict[str, Any]:
        if operation not in {"begin", "end", "stop", "stop_output"}:
            raise ValueError("Unsupported local voice command")
        async with self.lock:
            process = self.process
            if process is None or process.returncode is not None or process.stdin is None:
                raise ValueError("Start local voice first")
            identifier = uuid.uuid4().hex
            future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
            self.pending[identifier] = future
            try:
                process.stdin.write(
                    (json.dumps({"id": identifier, "op": operation}) + "\n").encode()
                )
                await process.stdin.drain()
                await asyncio.wait_for(future, 6)
            finally:
                self.pending.pop(identifier, None)
            return self.status()

    def invalidate(self, *, message: str = "Voice stopped after settings/access changed.") -> None:
        """Kill synchronously at static-policy change; no delayed recording after revocation."""
        self.lifecycle_epoch += 1
        self.presentation.reset()
        process, self.process = self.process, None
        self.microphone_open = None if process is not None and process.returncode is None else False
        self._fail_pending()
        if process is not None and process.stdin is not None:
            # Venv launchers can create a second Python process on Windows. Closing
            # the private pipe also delivers EOF to that actual audio worker.
            process.stdin.close()
        if process is not None and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        self.state, self.message = "stopped", message

    def _fail_pending(self) -> None:
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ValueError("Local voice worker stopped"))
        self.pending.clear()

    async def close(self) -> None:
        async with self.lock:
            await self._close()

    async def _close(self) -> None:
        self.invalidate(message="Local audio closed. The microphone is closed.")
        tasks = [task for task in (self.reader, self.stderr) if task is not None]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            self.microphone_open = False
        self.hearing = self.listening = False
        self.reader = self.stderr = None
