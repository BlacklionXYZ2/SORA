"""Native Laya through the ggmlc ``laya daemon``: one JSON line in, one JSON line out.

Laya (Convai Innovations, Apache 2.0) is a 421M-parameter ModernBERT-large decision model. The
GGUF from mys/laya-GGUF is compiled by ggmlc and is not a llama.cpp model, so it runs in its own
``laya.exe`` process, on the GPU through Vulkan. All family questions are answered in one encoder
pass (about 26 ms on the owner's RX 9070 XT; about 1.5 s on the CPU).

The layer fails open: if the runner is missing, slow or broken, ``decide`` returns None and the
brain is offered every tool, exactly as before the decision layer existed.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from sora import helper_processes
from sora.decision.families import FAMILIES, Family, laya_questions

MAX_STATE_CHARS = 1500  # Laya reads 512 tokens per question, including the question itself


@dataclass(frozen=True)
class Decision:
    probabilities: dict[str, float]  # family -> P(needed)
    families: frozenset[str]  # families at or above the threshold
    latency_ms: float
    model: str


class LayaDecisionLayer:
    def __init__(
        self,
        executable: Path,
        model: Path,
        *,
        device: str = "auto",
        timeout: float = 2.0,
        start_timeout: float = 90.0,
        families: tuple[Family, ...] = FAMILIES,
        command: tuple[str, ...] | None = None,  # tests: a stand-in daemon
    ) -> None:
        self.command = command
        self.executable = executable
        self.model = model
        self.device = device
        self.timeout = timeout
        self.start_timeout = start_timeout
        self.families = families
        self.questions = laya_questions(families)
        self.process: asyncio.subprocess.Process | None = None
        self.state = "stopped"
        self.reason = ""
        self._lock = asyncio.Lock()
        self._counter = 0

    def available(self) -> bool:
        return self.executable.is_file() and self.model.is_file()

    async def start(self) -> bool:
        async with self._lock:
            return await self._start()

    async def _start(self) -> bool:
        if self.process is not None and self.process.returncode is None:
            return True
        if self.command is None and not self.available():
            self.state, self.reason = "unavailable", "Run scripts/setup-decision-layer.ps1"
            return False
        self.state = "starting"
        try:
            argv = self.command or (
                str(self.executable), "daemon", str(self.model), "--device", self.device,
            )
            self.process = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0,  # no console window
            )
            helper_processes.record("laya", getattr(self.process, "pid", None))
            assert self.process.stdout is not None
            line = await asyncio.wait_for(self.process.stdout.readline(), self.start_timeout)
            if json.loads(line or b"{}").get("status") != "ready":
                raise ValueError("laya did not report ready")
        except (OSError, ValueError, TimeoutError) as exc:
            await self._stop(f"could not start ({exc})")
            return False
        self.state, self.reason = "ready", ""
        return True

    async def decide(
        self, text: str, *, threshold: float, agent_names: tuple[str, ...] = (),
    ) -> Decision | None:
        """Score every family for this message; None means "no decision, offer everything"."""
        async with self._lock:
            if not await self._start():
                return None
            process = self.process
            assert process is not None and process.stdin is not None and process.stdout is not None
            self._counter += 1
            request_id = str(self._counter)
            questions = (
                laya_questions(self.families, agent_names=agent_names)
                if agent_names else self.questions
            )
            request = {"id": request_id, "state": " ".join(text.split())[:MAX_STATE_CHARS],
                       "questions": questions}
            started = time.perf_counter()
            try:
                process.stdin.write(json.dumps(request).encode("utf-8") + b"\n")
                await process.stdin.drain()
                line = await asyncio.wait_for(process.stdout.readline(), self.timeout)
                reply = json.loads(line)
                if str(reply.get("id")) != request_id:
                    raise ValueError("laya answered a different request")
                answers = reply["answers"]
                probabilities = {
                    family.name: float(answers[family.name]["probabilities"]["A"])
                    for family in self.families
                }
            except (OSError, ValueError, KeyError, TypeError, TimeoutError) as exc:
                # A stuck or confused runner is restarted on the next message.
                await self._stop(f"failed ({type(exc).__name__}: {exc})")
                return None
        return Decision(
            probabilities=probabilities,
            families=frozenset(name for name, p in probabilities.items() if p >= threshold),
            latency_ms=(time.perf_counter() - started) * 1000,
            model=f"laya:{self.model.name}",
        )

    async def close(self) -> None:
        async with self._lock:
            await self._stop("")
        self.state = "stopped"

    async def _stop(self, reason: str) -> None:
        process, self.process = self.process, None
        if reason:
            self.state, self.reason = "failed", reason
        if process is None or process.returncode is not None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()  # the daemon ends at end of input
            await asyncio.wait_for(process.wait(), 3)
        except (TimeoutError, OSError):
            process.kill()
            await process.wait()
