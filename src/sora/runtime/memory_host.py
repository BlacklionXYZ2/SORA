"""Core's handle on the memory manager: follows Settings, runs in the background, never blocks
a reply, and chooses which memories go in her context.

Like the decision layer, it is off until an owner launch turns it on (Core's --listen-on-start),
so tests and embedded runtimes never start the embedding server.

- shadow (default): memories are embedded, linked and logged after they are made. Each turn
  records what meaning-based recall would have chosen next to today's recency recall
  (``memory_recalls`` rows and a ``memory.recall`` trace); her context is unchanged.
- on: her context gets the memories most relevant to the message (up to ten, above the
  relevance floor), then the most recent ones fill any remaining places, so standing
  instructions ("always answer briefly") stay in view.
- off: nothing runs.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sora.memory.embedder import EmbedderConfig, EmbedderError, LlamaEmbedder
from sora.memory.features import words
from sora.memory.layers import LayerSet
from sora.memory.manager import DecisionLog, ManagerRun, MemoryManager
from sora.memory.settings import MemoryManagerSettings, resolve_paths
from sora.memory.store import MemoryVectorStore, RecallMode
from sora.persistence.records import StoredMemory
from sora.persistence.repository import SoraRepository

PROJECT_ROOT = Path(__file__).resolve().parents[3]
STARTUP_DELAY_SECONDS = 20.0  # let the brain load first
RECALL_TIMEOUT_SECONDS = 1.5  # "on" mode falls back to recency rather than delay a reply

Trace = Callable[[str, str, dict[str, Any]], Awaitable[None]]


def shared_words_first(text: str, recent: Sequence[StoredMemory],
                       candidates: Sequence[StoredMemory], limit: int) -> list[StoredMemory]:
    """Up to half the places for memories sharing content words with the message (most words
    first), then the most recent. Cheap, and needs no embedder."""
    wanted = words(text)
    scored = sorted(((len(wanted & words(m.content)), index, m)
                     for index, m in enumerate(candidates)), key=lambda row: (-row[0], -row[1]))
    chosen = [m for score, _, m in scored if score > 0][: max(1, limit // 2)]
    for memory in reversed(recent):
        if len(chosen) >= limit:
            break
        if memory not in chosen:
            chosen.append(memory)
    return chosen if wanted else list(recent)


class MemoryHost:
    def __init__(
        self, *, repository: SoraRepository, state_root: Path, owner_id: str,
        project_id: str | None, captures_root: Path, trace: Trace,
        settings: Callable[[], MemoryManagerSettings], project: Path = PROJECT_ROOT,
    ) -> None:
        self.repository = repository
        self.state_root = state_root
        self.owner_id = owner_id
        self.project_id = project_id
        self.captures_root = captures_root
        self.trace = trace
        self.project = project
        self.enabled = False
        self._settings = settings
        self.store = MemoryVectorStore(repository.database)
        self.layers = LayerSet(state_root / "memory" / "layers")
        self.embedder: LlamaEmbedder | None = None
        self.manager: MemoryManager | None = None
        self._identity: tuple[Path, Path, str] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._wanted = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._chosen: OrderedDict[str, list[StoredMemory]] = OrderedDict()
        self.last_run: ManagerRun | None = None

    @property
    def settings(self) -> MemoryManagerSettings:
        return self._settings()

    def _manager(self) -> MemoryManager | None:
        if not self.enabled or self.settings.mode == "off":
            return None
        server, model = resolve_paths(self.settings, self.project)
        identity = (server, model, self.settings.device)
        if self.manager is None or identity != self._identity:
            if self.embedder is not None:
                self._spawn(self.embedder.close())
            # The image/audio projector beside the model, when installed (setup -WithMedia).
            mmproj = next(iter(sorted(model.parent.glob("mmproj*.gguf"))), None) \
                if model.parent.is_dir() else None
            self.embedder = LlamaEmbedder(EmbedderConfig(
                server=server, model=model, mmproj=mmproj,
                gpu_layers="0" if self.settings.device == "cpu" else "99",
                log=self.state_root / "logs" / "memory-embedder.log"))
            if not self.embedder.available():
                self.manager = None
                self._identity = identity
                return None
            self.manager = MemoryManager(
                repository=self.repository, store=self.store, embedder=self.embedder,
                layers=self.layers, log=DecisionLog(self.state_root / "memory" / "decisions"),
                owner_id=self.owner_id, project_id=self.project_id,
                captures_root=self.captures_root,
                entries_root=self.state_root / "memory" / "entries")
            self._identity = identity
        return self.manager

    def start(self) -> None:
        """Owner launches: work through memories that have no vectors yet, in the background."""
        self.enabled = True
        if self._manager() is None:
            return
        self._worker = asyncio.create_task(self._work(), name="sora-memory-manager")
        self.nudge()

    def nudge(self) -> None:
        """A memory was made: process it soon, after any current run."""
        if self._worker is not None:
            self._wanted.set()

    async def _work(self) -> None:
        await asyncio.sleep(STARTUP_DELAY_SECONDS)
        while True:
            await self._wanted.wait()
            self._wanted.clear()
            manager = self._manager()
            if manager is None:
                continue
            try:
                self.last_run = run = await manager.run(budget=20)
            except EmbedderError as exc:
                await self.trace("memory-manager", "memory.manager",
                                 {"version": 1, "error": str(exc)})
                continue
            except Exception as exc:  # the manager must never take Core down
                await self.trace("memory-manager", "memory.manager",
                                 {"version": 1, "error": type(exc).__name__})
                continue
            if run.embedded:
                await self.trace("memory-manager", "memory.manager", {
                    "version": 1, "embedded": run.embedded, "links": run.links,
                    "kinds": run.kinds, "decisions": run.decisions,
                    "remaining": run.remaining})
            if run.remaining:
                self._wanted.set()

    async def select(
        self, text: str, recent: Sequence[StoredMemory], candidates: Sequence[StoredMemory],
        *, limit: int, correlation_id: str,
    ) -> list[StoredMemory]:
        """The memories for this turn's context. ``recent`` is today's choice (the last
        ``limit``); ``candidates`` are every memory recall may choose from."""
        if correlation_id and correlation_id in self._chosen:
            return self._chosen[correlation_id]  # the same turn rebuilt its context
        manager = self._manager()
        # Without meaning-based recall, memories sharing words with the message come first, so
        # an older fact is not lost behind ten newer ones (live, 2026-10-10: "What am I allergic
        # to?" missed the 3rd of 13 memories).
        chosen = shared_words_first(text, recent, candidates, limit)
        if manager is not None and text.strip():
            if self.settings.mode == "on":
                try:
                    async with asyncio.timeout(RECALL_TIMEOUT_SECONDS):
                        chosen = await self._recall(manager, text, recent, candidates, limit,
                                                    correlation_id, record_recency=False)
                except (TimeoutError, EmbedderError):
                    pass  # keep the shared-words choice
            else:
                self._spawn(self._recall(manager, text, recent, candidates, limit,
                                         correlation_id, record_recency=True))
        if correlation_id:
            self._chosen[correlation_id] = chosen
            while len(self._chosen) > 8:
                self._chosen.popitem(last=False)
        return chosen

    async def _recall(
        self, manager: MemoryManager, text: str, recent: Sequence[StoredMemory],
        candidates: Sequence[StoredMemory], limit: int, correlation_id: str,
        *, record_recency: bool,
    ) -> list[StoredMemory]:
        try:
            ranked = await manager.recall(text, candidates)
        except EmbedderError:
            if record_recency:
                return list(recent)  # shadow: nothing to compare with
            raise
        by_id = {m.memory_id: m for m in candidates}
        chosen = [by_id[r.memory_id] for r in ranked[:limit]]
        for memory in reversed(recent):  # most recent first, to fill the remaining places
            if len(chosen) >= limit:
                break
            if memory not in chosen:
                chosen.append(memory)
        mode: RecallMode = "shadow" if record_recency else "meaning"
        correlation = correlation_id or f"recall-{datetime.now(UTC).timestamp()}"
        await self.store.record_recalls(correlation, mode,
                                        [(r.memory_id, round(r.relevance, 4)) for r in ranked])
        if record_recency:
            await self.store.record_recalls(correlation, "recency",
                                            [(m.memory_id, None) for m in reversed(recent)])
        await self.trace(correlation, "memory.recall", {
            "version": 1, "mode": self.settings.mode,
            "meaning": [[r.memory_id, round(r.relevance, 3)] for r in ranked],
            "recency": [m.memory_id for m in recent],
            "overlap": len({r.memory_id for r in ranked} & {m.memory_id for m in recent}),
        })
        return chosen

    def _spawn(self, work: Awaitable[Any]) -> None:
        async def run() -> None:
            try:
                await work
            except Exception:
                pass  # shadow work never affects a turn

        task = asyncio.create_task(run(), name="sora-memory-shadow")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def status(self) -> dict[str, Any]:
        embedder = self.embedder
        return {
            "mode": self.settings.mode, "enabled": self.enabled,
            "embedder": embedder.state if embedder else "stopped",
            "reason": embedder.reason if embedder else "",
            "layers": {name: self.layers.policy(name)
                       for name in ("acceptance", "relevance", "same_subject", "update")},
        }

    async def close(self) -> None:
        worker, self._worker = self._worker, None
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        embedder, self.embedder, self.manager = self.embedder, None, None
        if embedder is not None:
            await embedder.close()
