"""The memory manager (MEMORY_MANAGER_2026-10-08 §3): embed, accept, choose parts, link, recall.

It runs in the background after a memory is made and at startup, never in front of a reply.
For each memory without vectors from the current embedder it:

1. embeds the owner's words (document and similarity forms) and, while the turn's capture still
   exists, her reply;
2. compares it with every stored memory: ``same_subject`` (a repeat or an update), ``update``
   (the newer replaces the older) and up to five ``related`` links;
3. scores acceptance (keep?) and the reply part's relevance;
4. stores the vectors and links, and appends every decision, with its features, to
   ``<state>/memory/decisions/<date>.jsonl`` as a training example.

Each decision uses the trained layer when one is active, otherwise the fixed thresholds.
Decisions that would remove or replace something the owner told her (withdrawing a memory,
marking one superseded) are only recorded as links and log lines for now. They take effect only
after the owner can review them in the Memory window (plan step 5). Logs hold IDs and
features, never memory text, so deleting a memory leaves no copy behind.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from sora.memory import features
from sora.memory.authors import is_own_thought
from sora.memory.captures import list_captures
from sora.memory.embedder import Embedder, EmbedderError
from sora.memory.entries import PartVerdict, TurnEntry, media_bytes, read_entry, save_entry
from sora.memory.features import Thresholds
from sora.memory.layers import LayerSet
from sora.memory.store import Link, MemoryVectorStore
from sora.memory.vectors import Vector, cosine, mean_vector, project, top_k
from sora.persistence.records import StoredMemory
from sora.persistence.repository import SoraRepository

MANAGER_VERSION = "memory-manager-1"
TEXT_PARTS = ("owner", "words", "reply", "read")  # document-form parts recall searches
IMAGE_PREFIX, VOICE_PART = "image", "voice"  # media parts, with their own floors


class DecisionLog:
    """Append-only JSONL training examples, one file per day."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def append(self, record: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        with target.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")


@dataclass
class ManagerRun:
    embedded: int = 0
    links: int = 0
    decisions: int = 0
    remaining: int = 0
    error: str = ""
    kinds: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Recalled:
    memory_id: str
    relevance: float  # similarity of the best part to the current message
    score: float  # relevance + importance and recency tie-breakers


class MemoryManager:
    def __init__(
        self, *, repository: SoraRepository, store: MemoryVectorStore, embedder: Embedder,
        layers: LayerSet, log: DecisionLog, owner_id: str, project_id: str | None,
        captures_root: Path, thresholds: Thresholds | None = None,
        entries_root: Path | None = None,
    ) -> None:
        self.repository = repository
        self.store = store
        self.embedder = embedder
        self.layers = layers
        self.log = log
        self.owner_id = owner_id
        self.project_id = project_id
        self.captures_root = captures_root
        self.entries_root = entries_root
        self.thresholds = thresholds or Thresholds()
        self._prototypes: tuple[list[Vector], list[Vector]] | None = None
        self._lock = asyncio.Lock()

    async def prototypes(self) -> tuple[list[Vector], list[Vector]]:
        if self._prototypes is None:
            personal = [await self.embedder.embed(t, "similarity") for t in features.PERSONAL]
            chatter = [await self.embedder.embed(t, "similarity") for t in features.CHATTER]
            self._prototypes = (personal, chatter)
        return self._prototypes

    async def run(self, budget: int = 20) -> ManagerRun:
        """Process up to ``budget`` memories that have no vectors from this embedder."""
        async with self._lock:
            return await self._run(budget)

    async def _run(self, budget: int) -> ManagerRun:
        result = ManagerRun()
        self.layers.reload()  # a layer adopted by training applies from the next run
        now = datetime.now(UTC)
        memories = await self.repository.list_memories(
            self.owner_id, project_id=self.project_id, observed_at=now)
        done = await self.store.embedded_ids(self.embedder.identity, "whole")
        pending = sorted((m for m in memories if m.memory_id not in done),
                         key=lambda m: m.created_at or now)
        result.remaining = max(0, len(pending) - budget)
        if not pending:
            return result
        replies = await asyncio.to_thread(self._replies)
        dated = {m.memory_id: m.created_at for m in memories}
        existing = [(mid, v) for mid, _, v in
                    await self.store.vectors(self.embedder.identity, "whole")]
        texts = {m.memory_id: m.content for m in memories}
        for memory in pending[:budget]:
            parts, links, logged = await self._process(memory, replies.get(memory.memory_id),
                                                       existing, dated, texts)
            await self.store.put(memory.memory_id, parts, embedder=self.embedder.identity)
            await self.store.add_links(links)
            existing.append((memory.memory_id, parts["whole"]))
            result.embedded += 1
            result.links += len(links)
            result.decisions += logged
            for link in links:
                result.kinds[link.kind] = result.kinds.get(link.kind, 0) + 1
        return result

    async def _process(
        self, memory: StoredMemory, reply: str | None, existing: Sequence[tuple[str, Vector]],
        dated: Mapping[str, datetime | None], texts: Mapping[str, str],
    ) -> tuple[dict[str, Vector], list[Link], int]:
        """Parts first (each judged for relevance to her description, irrelevant media
        deleted), then the whole memory from what was kept, then links from the whole."""
        th = self.thresholds
        parts: dict[str, Vector] = {"owner": await self.embedder.embed(memory.content,
                                                                       "document")}
        anchor = await self.embedder.embed(memory.content, "similarity")
        when = memory.created_at or datetime.now(UTC)
        logged = 0
        kept_text: list[str] = []
        kept_media: list[tuple[bytes, Literal["image", "audio"]]] = []

        # Stage B: the turn's other parts. A remember-tool memory has a full entry (her reply,
        # what was read, images, the owner's voice); older memories have only the reply, while
        # the turn's capture still exists.
        entry = (read_entry(self.entries_root, memory.memory_id)
                 if self.entries_root is not None else None)
        if entry is not None:
            logged += await self._entry_parts(memory, entry, anchor, parts, kept_text,
                                              kept_media)
        elif reply and reply.strip():
            logged += await self._text_part(memory, "reply", "reply", reply, anchor, parts,
                                            kept_text)

        # The whole memory: one embedding of her description with every kept part, a numerical
        # summary of the moment. It decides which memories are alike and places the memory on
        # the map; part vectors are for relevance within the memory and for recall.
        whole = await self._whole(memory.content, kept_text, kept_media)
        parts["whole"] = whole

        # Stage D: compare the whole memory with every stored whole memory.
        candidates = top_k(whole, existing, k=50, floor=th.related,
                           exclude=frozenset({memory.memory_id}))
        links: list[Link] = []
        related: list[tuple[str, float]] = []
        for other_id, similarity in candidates:
            other_when = dated.get(other_id) or when
            values = features.comparison(memory.content, texts.get(other_id, ""), similarity,
                                         abs((when - other_when).total_seconds()) / 86_400)
            same, p_same = self._decide("same_subject", values,
                                        lambda v: v["similarity"] >= th.same_subject)
            logged += self._record("same_subject", memory.memory_id, values, same, p_same,
                                   other_id=other_id)
            if same:
                links.append(Link(memory.memory_id, other_id, "same_subject", similarity,
                                  self.layers.policy("same_subject")))
                update, p_update = self._decide(
                    "update", values,
                    lambda v: bool(v["change_marker"] or v["number_mismatch"]
                                   or v["negation_mismatch"]))
                logged += self._record("update", memory.memory_id, values, update, p_update,
                                       other_id=other_id)
                if update:
                    links.append(Link(memory.memory_id, other_id, "update", similarity,
                                      self.layers.policy("update")))
            else:
                related.append((other_id, similarity))
        links += [Link(memory.memory_id, other_id, "related", score, "fixed-threshold")
                  for other_id, score in related[: th.related_links]]

        # Stage A: keep this memory?
        personal, chatter = await self.prototypes()
        recent = sum(
            1 for other_id, _ in candidates
            if abs(((dated.get(other_id) or when) - when).total_seconds()) <= 7 * 86_400)
        values = features.acceptance(
            memory.content,
            nearest_similarity=max((cosine(whole, v) for i, v in existing
                                    if i != memory.memory_id), default=0.0),
            similar_recent=recent,
            personal=features.prototype_score(anchor, personal),
            chatter=features.prototype_score(anchor, chatter),
            own_thought=is_own_thought(memory),
        )
        keep, p_keep = self._decide("acceptance", values, lambda v: v["nominated"] >= 1)
        logged += self._record("acceptance", memory.memory_id, values, keep, p_keep)
        return parts, links, logged

    async def _whole(self, description: str, texts: Sequence[str],
                     media: Sequence[tuple[bytes, Literal["image", "audio"]]]) -> Vector:
        text = "\n".join([description, *texts])[:6_000]
        usable = [data for data, kind in media if kind in self.embedder.modalities]
        if usable:
            try:
                return await self.embedder.embed_mixed(text, "similarity", usable)
            except EmbedderError:
                pass  # the text alone still summarises the memory
        return await self.embedder.embed(text, "similarity")

    async def _text_part(self, memory: StoredMemory, name: str, kind: str, text: str,
                         anchor: Vector, parts: dict[str, Vector], kept: list[str],
                         entry: TurnEntry | None = None) -> int:
        th = self.thresholds
        doc = await self.embedder.embed(text[:4_000], "document")
        sim = await self.embedder.embed(text[:4_000], "similarity")
        relevance = cosine(sim, anchor)  # unit vectors: the dot product is the cosine
        values = features.relevance(
            kind, similarity_to_owner=relevance,
            similarity_to_entry=cosine(sim, mean_vector([anchor, sim])),
            max_similarity_same_type=0.0, size=len(text))
        relevant, probability = self._decide(
            "relevance", values, lambda v: v["similarity_to_owner"] >= th.part_relevance)
        if relevant:
            parts[name] = doc
            kept.append(text[:2_000])
        if entry is not None:
            entry.parts[name] = PartVerdict(kept=relevant, relevance=round(relevance, 4),
                                            policy=self.layers.policy("relevance"))
        return self._record("relevance", memory.memory_id, values, relevant, probability,
                            part=name)

    async def _entry_parts(
        self, memory: StoredMemory, entry: TurnEntry, anchor: Vector, parts: dict[str, Vector],
        kept_text: list[str], kept_media: list[tuple[bytes, Literal["image", "audio"]]],
    ) -> int:
        """Every part of a remembered turn. The owner's words are always kept (verbatim, the
        anchor of what the memory is about). The rest are scored against her description, and
        images or recordings that aren't relevant are deleted, not stored."""
        th = self.thresholds
        logged = 0
        root = self.entries_root
        assert root is not None
        if entry.owner_text.strip():
            parts["words"] = await self.embedder.embed(entry.owner_text[:4_000], "document")
            entry.parts["words"] = PartVerdict(kept=True, policy="always kept")
            kept_text.append(entry.owner_text[:2_000])
        if entry.reply.strip():
            logged += await self._text_part(memory, "reply", "reply", entry.reply, anchor,
                                            parts, kept_text, entry)
        if entry.read_observations.strip():
            logged += await self._text_part(memory, "read", "read",
                                            entry.read_observations[:2_000], anchor, parts,
                                            kept_text, entry)
        query = await self.embedder.embed(memory.content, "query")
        seen_images: list[Vector] = []
        remaining = []
        for media in entry.media:
            kind: Literal["image", "audio"] = "audio" if media.source == "voice" else "image"
            name = media.file.rsplit(".", 1)[0]
            if kind not in self.embedder.modalities:
                # Kept until it can be judged: embedded once a projector is installed.
                entry.parts[name] = PartVerdict(kept=True, policy="not embedded (text-only)")
                remaining.append(media)
                continue
            try:
                data = media_bytes(root, entry, media)
                vector = await self.embedder.embed_media(data, kind)
            except (OSError, ValueError, EmbedderError):
                entry.parts[name] = PartVerdict(kept=True, policy="not embedded (failed)")
                remaining.append(media)
                continue
            relevance = cosine(query, vector)  # unit vectors: the dot product is the cosine
            duplicate = max((cosine(vector, other) for other in seen_images), default=0.0)
            values = features.relevance(
                kind, similarity_to_owner=relevance, similarity_to_entry=relevance,
                max_similarity_same_type=duplicate, size=media.bytes / 1000)
            relevant, probability = self._decide(
                "relevance", values,
                lambda v: v["similarity_to_owner"] >= th.audio_relevance
                if v["type_audio"] == 1 else (
                    v["similarity_to_owner"] >= th.image_relevance
                    and v["max_similarity_same_type"] < th.image_duplicate))
            logged += self._record("relevance", memory.memory_id, values, relevant,
                                   probability, part=name)
            if relevant:
                parts[name] = vector
                kept_media.append((data, kind))
                remaining.append(media)
                if kind == "image":
                    seen_images.append(vector)
                entry.parts[name] = PartVerdict(kept=True, relevance=round(relevance, 4),
                                                policy=self.layers.policy("relevance"))
            else:
                try:  # not relevant to this memory: not stored
                    (root / entry.memory_id / media.file).unlink()
                except OSError:
                    remaining.append(media)
                entry.parts[name] = PartVerdict(kept=False, relevance=round(relevance, 4),
                                                policy=self.layers.policy("relevance"))
        try:
            save_entry(root, entry.model_copy(update={"status": "processed",
                                                      "media": remaining}))
        except OSError:
            pass
        return logged

    async def map_coordinates(self, dims: int = 2) -> dict[str, tuple[float, ...]]:
        """The memory graph's positions: PCA of the whole-memory vectors (plan §3.8)."""
        rows = await self.store.vectors(self.embedder.identity, "whole")
        return dict(zip([mid for mid, _, _ in rows], project([v for _, _, v in rows], dims),
                        strict=True))

    def _decide(self, layer: str, values: Mapping[str, float],
                fixed: Any) -> tuple[bool, float | None]:
        trained = self.layers.get(layer)
        if trained is not None:
            probability = trained.probability(values)
            return probability >= trained.threshold, probability
        return bool(fixed(values)), None

    def _record(self, layer: str, memory_id: str, values: Mapping[str, float], decision: bool,
                probability: float | None, *, other_id: str | None = None,
                part: str | None = None) -> int:
        try:
            self.log.append({
                "id": f"decision-{uuid.uuid4()}", "at": datetime.now(UTC).isoformat(),
                "layer": layer, "memory_id": memory_id, "other_id": other_id, "part": part,
                "features": {k: round(v, 5) for k, v in values.items()},
                "decision": decision, "probability": probability,
                "policy": self.layers.policy(layer), "embedder": self.embedder.identity,
                "manager": MANAGER_VERSION,
            })
        except OSError:
            return 0  # logging never stops the manager
        return 1

    def _replies(self) -> dict[str, str]:
        return {record.memory_id: record.response_text
                for _, record in list_captures(self.captures_root)
                if record.memory_id and record.response_text}

    async def recall(self, text: str, memories: Sequence[StoredMemory],
                     *, now: datetime | None = None) -> list[Recalled]:
        """Memories relevant to this message, best part first (§10b): candidates above the
        relevance floor, ranked by relevance + a·importance + b·recency."""
        th = self.thresholds
        now = now or datetime.now(UTC)
        query = await self.embedder.embed(text, "query")
        live = {m.memory_id: m for m in memories}
        rows = [(mid, part, v) for mid, part, v in
                await self.store.vectors(self.embedder.identity) if mid in live]
        written = [(mid, v) for mid, part, v in rows if part in TEXT_PARTS]
        best = dict(top_k(query, written, k=len(written) or 1, floor=th.recall_floor))
        for prefix, floor in ((IMAGE_PREFIX, th.image_relevance),
                              (VOICE_PART, th.audio_relevance)):
            media = [(mid, v) for mid, part, v in rows if part.startswith(prefix)]
            for memory_id, score in top_k(query, media, k=len(media) or 1, floor=floor):
                # A picture or recording matched: count it on the text scale, from the floor.
                best[memory_id] = max(best.get(memory_id, 0.0),
                                      th.recall_floor + score - floor)
        ranked: list[Recalled] = []
        for memory_id, relevance in best.items():
            created = live[memory_id].created_at
            age_days = (now - created).total_seconds() / 86_400 if created else 365.0
            importance = 0.5  # until the acceptance layer's confidence is stored (§5)
            score = (relevance + th.importance_weight * importance
                     + th.recency_weight * math.exp(-max(0.0, age_days) / th.recency_days))
            ranked.append(Recalled(memory_id, relevance, score))
        ranked.sort(key=lambda item: item.score, reverse=True)
        return ranked[: th.recall_limit]
