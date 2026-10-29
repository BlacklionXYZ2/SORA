"""Which motion engine moves her, and the motion model process when it is one (2026-10-27).

Settings → Motion chooses the engine; **Reload motion model** (``POST /api/v1/motion/reload``)
applies it while SORA runs, the way Reload model applies the brain. A reload:

1. stops the current motion model, if any, and tells her player to use its own (algorithmic)
   poses, so she never freezes;
2. asks the player to start **recording** her actual pose;
3. starts the model (motion-lab's ``ardy-runtime/service.py``) and waits for it to load
   (about 7 s, of which 2 s loading the model);
4. asks the player for the recording and hands it to the model as **seed** history, so the model
   continues exactly where she is; with no recording within 3 s, the model starts standing;
5. relays the model's 0.4 s chunks of canonical 60 Hz poses to the player, and switches the
   player's **source** to the model.

The player sends what she is doing (a phrase key and the velocity she should travel at), which
is passed on to the model. A model that fails to load, errors or stops leaves her on the
algorithmic system, with the reason in :meth:`status`.

Nothing here touches durable state: the stream is presentation only, like ``embodiment.voice``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import ValidationError

from sora import helper_processes
from sora.contracts.motion_stream import (
    CoreMotionMessage,
    MotionChunk,
    PlayerMotionMessage,
)
from sora.embodiment.motion_settings import MotionSettings, resolve_lab

MotionState = Literal["algorithmic", "starting", "handover", "running", "failed"]
RECORD_SECONDS = 3.0
SEED_WAIT_SECONDS = 3.0
START_TIMEOUT_SECONDS = 90.0
QUEUE_SIZE = 64
STANDING = ("-|-|-", [0.0, 0.0])


def service_command(settings: MotionSettings, project: Path) -> list[str]:
    """The ARDY service's command line; raises ``FileNotFoundError`` naming what is missing."""
    runtime = resolve_lab(settings, project) / "ardy-runtime"
    python = runtime / ".venv" / "Scripts" / "python.exe"
    script = runtime / "service.py"
    for path in (python, script, runtime / "assets" / "phrases.npz"):
        if not path.is_file():
            raise FileNotFoundError(f"{path} is missing")
    return [str(python), str(script), "--precision", settings.ardy_precision,
            "--steps", str(settings.ardy_steps)]


class MotionSupervisor:
    def __init__(self, project: Path) -> None:
        self.project = project
        self.state: MotionState = "algorithmic"
        self.engine = "algorithmic"
        self.error = ""
        self.model = ""
        self.load_seconds: float | None = None
        self.chunks = 0
        self.process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.Task[None] | None = None
        self._handover: asyncio.Task[None] | None = None
        self._seed: asyncio.Future[dict[str, Any]] | None = None
        self._signal: tuple[str, list[float]] = STANDING
        self._listeners: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = asyncio.Lock()
        self._generation = 0  # bumped by every reload, so a stale process's output is ignored

    # ---------- the player's connection ----------

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self._listeners.append(queue)
        # A (re)connected player learns the current source at once.
        queue.put_nowait(self._message("source", source="ardy" if self.state == "running"
                                       else "algorithmic"))
        return queue

    def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._listeners:
            self._listeners.remove(queue)

    @staticmethod
    def _message(op: str, **fields: Any) -> dict[str, Any]:
        return CoreMotionMessage.model_validate({"op": op, **fields}).model_dump(
            mode="json", exclude_none=True)

    def _publish(self, message: dict[str, Any]) -> None:
        for queue in self._listeners:
            if queue.full():
                # A stalled player: drop its backlog rather than play stale motion late.
                while not queue.empty():
                    queue.get_nowait()
            queue.put_nowait(message)

    async def from_player(self, data: dict[str, Any]) -> None:
        """A ``embodiment.motion`` message from her player (validated here)."""
        message = PlayerMotionMessage.model_validate(
            {k: v for k, v in data.items() if k != "type"})
        if message.op == "seed":
            assert message.seed is not None
            if self._seed is not None and not self._seed.done():
                self._seed.set_result(message.seed.model_dump(mode="json"))
            return
        assert message.key is not None and message.velocity is not None
        self._signal = (message.key, list(message.velocity))
        await self._send({"type": "signal", "key": message.key, "velocity": message.velocity})

    # ---------- status ----------

    def status(self) -> dict[str, Any]:
        return {
            "engine": self.engine, "state": self.state, "model": self.model,
            "error": self.error, "load_seconds": self.load_seconds, "chunks": self.chunks,
            "player_connected": bool(self._listeners),
        }

    # ---------- reload ----------

    async def reload(self, settings: MotionSettings) -> dict[str, Any]:
        """Apply ``settings``: stop the current model, then start the chosen one (returns as
        soon as it is starting; the handover continues in the background)."""
        async with self._lock:
            self._generation += 1
            await self._stop()
            self.engine, self.error, self.model = settings.engine, "", ""
            self.load_seconds, self.chunks = None, 0
            self._publish(self._message("source", source="algorithmic"))
            if settings.engine == "algorithmic":
                self.state = "algorithmic"
                return self.status()
            if settings.engine == "custom":
                self.state = "failed"
                self.error = ("SORA's own trained models can't drive her yet; only ARDY can. She "
                              "keeps the algorithmic system.")
                return self.status()
            try:
                command = service_command(settings, self.project)
            except FileNotFoundError as exc:
                self.state, self.error = "failed", f"ARDY isn't installed: {exc}"
                return self.status()
            self.state, self.model = "starting", f"ARDY Core {settings.ardy_precision}"
            self._publish(self._message("record", seconds=RECORD_SECONDS))
            self._handover = asyncio.create_task(
                self._start(command, self._generation), name="motion-service")
            return self.status()

    async def _start(self, command: list[str], generation: int) -> None:
        started = time.perf_counter()
        try:
            self.process = await asyncio.create_subprocess_exec(
                *command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=4 * 1024 * 1024)
            helper_processes.record("motion", getattr(self.process, "pid", None))
            ready = await asyncio.wait_for(self._read(), START_TIMEOUT_SECONDS)
            if ready is None or ready.get("type") != "ready":
                detail = (ready or {}).get("message", "it stopped while loading")
                raise RuntimeError(str(detail)[:300])
            if generation != self._generation:
                return
            self.load_seconds = round(time.perf_counter() - started, 1)
            self.state = "handover"
            self._seed = asyncio.get_running_loop().create_future()
            self._publish(self._message("seed_request"))
            try:
                seed = await asyncio.wait_for(self._seed, SEED_WAIT_SECONDS)
                await self._send({"type": "seed", **seed})
            except TimeoutError:
                await self._send({"type": "start"})  # no recording: she starts standing
            key, velocity = self._signal
            await self._send({"type": "signal", "key": key, "velocity": velocity})
            self._reader = asyncio.create_task(self._relay(generation), name="motion-relay")
        except Exception as exc:  # noqa: BLE001 - any failure leaves her on her own poses
            if generation == self._generation:
                self.state = "failed"
                self.error = f"The motion model didn't start: {exc}"[:400]
                self._publish(self._message("source", source="algorithmic"))
                await self._stop_process()

    async def _relay(self, generation: int) -> None:
        switched = False
        while generation == self._generation:
            message = await self._read()
            if message is None:
                if generation == self._generation:
                    self.state, self.error = "failed", "The motion model stopped."
                    self._publish(self._message("source", source="algorithmic"))
                return
            kind = message.get("type")
            if kind == "chunk":
                try:
                    chunk = MotionChunk.model_validate(
                        {k: v for k, v in message.items() if k != "type"})
                except ValidationError:
                    continue
                self.chunks += 1
                self._publish(self._message("chunk", chunk=chunk.model_dump(mode="json")))
                if not switched:
                    # The first chunk is on its way: hand her over from her own poses.
                    self._publish(self._message("source", source="ardy"))
                    self.state, switched = "running", True
            elif kind == "error":
                self.error = str(message.get("message", ""))[:400]

    async def _read(self) -> dict[str, Any] | None:
        assert self.process is not None and self.process.stdout is not None
        while True:
            line = await self.process.stdout.readline()
            if not line:
                return None
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data

    async def _send(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None or process.returncode is not None:
            return
        try:
            process.stdin.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
            await process.stdin.drain()
        except (ConnectionError, OSError):
            pass

    async def _stop(self) -> None:
        for task in (self._handover, self._reader):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self._handover = self._reader = None
        if self._seed is not None and not self._seed.done():
            self._seed.cancel()
        self._seed = None
        await self._stop_process()

    async def _stop_process(self) -> None:
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        with contextlib.suppress(ConnectionError, OSError):
            if process.stdin is not None:
                process.stdin.write(b'{"type":"stop"}\n')
                await process.stdin.drain()
                process.stdin.close()  # the service also stops when its input closes
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()

    async def close(self) -> None:
        async with self._lock:
            self._generation += 1
            await self._stop()
            self.state = "algorithmic"
