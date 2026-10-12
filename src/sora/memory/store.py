"""Memory vectors, links and recall records (migration 14). Memories themselves stay in
``SoraRepository``; this store only adds what the memory manager derives from them."""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from sora.memory.vectors import Vector, pack, unpack
from sora.persistence.database import SQLiteDatabase

LinkKind = Literal["same_subject", "update", "related"]
RecallMode = Literal["recency", "meaning", "shadow"]


@dataclass(frozen=True)
class Link:
    source_id: str  # the newer memory
    target_id: str  # the older memory it was compared with
    kind: LinkKind
    score: float
    decided_by: str  # "fixed-threshold" or "layer:<version>"


def _now() -> str:
    return datetime.now(UTC).isoformat()


class MemoryVectorStore:
    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database

    async def embedded_ids(self, embedder: str, part: str) -> set[str]:
        def read(db: sqlite3.Connection) -> set[str]:
            rows = db.execute("SELECT memory_id FROM memory_vectors WHERE embedder=? AND part=?",
                              (embedder, part)).fetchall()
            return {str(row[0]) for row in rows}

        return await self.database.read(read)

    async def put(self, memory_id: str, parts: Mapping[str, Vector], *, embedder: str) -> None:
        def write(db: sqlite3.Connection) -> None:
            now = _now()
            for part, vector in parts.items():
                db.execute(
                    "INSERT OR REPLACE INTO memory_vectors(memory_id, part, embedder, dims, "
                    "vector, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (memory_id, part, embedder, len(vector), pack(vector), now),
                )

        await self.database.write(write)

    async def vectors(
        self, embedder: str, part: str | None = None,
    ) -> list[tuple[str, str, Vector]]:
        """(memory_id, part, vector) for memories that are neither deleted nor superseded."""

        def read(db: sqlite3.Connection) -> list[tuple[str, str, Vector]]:
            rows = db.execute(
                "SELECT v.memory_id, v.part, v.vector FROM memory_vectors v JOIN memories m "
                "ON m.memory_id=v.memory_id WHERE v.embedder=? AND (? IS NULL OR v.part=?) "
                "AND m.deleted_at IS NULL AND m.superseded_by IS NULL",
                (embedder, part, part),
            ).fetchall()
            return [(str(r[0]), str(r[1]), unpack(bytes(r[2]))) for r in rows]

        return await self.database.read(read)

    async def add_links(self, links: Sequence[Link]) -> None:
        def write(db: sqlite3.Connection) -> None:
            now = _now()
            for link in links:
                db.execute(
                    "INSERT OR REPLACE INTO memory_links(source_id, target_id, kind, score, "
                    "decided_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (link.source_id, link.target_id, link.kind, link.score, link.decided_by, now),
                )

        if links:
            await self.database.write(write)

    async def links(self, memory_id: str) -> list[Link]:
        def read(db: sqlite3.Connection) -> list[Link]:
            rows = db.execute(
                "SELECT source_id, target_id, kind, score, decided_by FROM memory_links "
                "WHERE source_id=? OR target_id=? ORDER BY score DESC", (memory_id, memory_id),
            ).fetchall()
            return [Link(str(r[0]), str(r[1]), r[2], float(r[3]), str(r[4])) for r in rows]

        return await self.database.read(read)

    async def record_recalls(
        self, correlation_id: str, mode: RecallMode,
        ranked: Sequence[tuple[str, float | None]],
    ) -> None:
        def write(db: sqlite3.Connection) -> None:
            now = _now()
            for rank, (memory_id, relevance) in enumerate(ranked, start=1):
                db.execute(
                    "INSERT INTO memory_recalls(recall_id, memory_id, correlation_id, mode, rank, "
                    "relevance, used, recalled_at) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
                    (f"recall-{uuid.uuid4()}", memory_id, correlation_id, mode, rank, relevance,
                     now),
                )

        if ranked:
            await self.database.write(write)

    async def recall_counts(self) -> dict[str, int]:
        def read(db: sqlite3.Connection) -> dict[str, int]:
            rows = db.execute("SELECT mode, COUNT(*) FROM memory_recalls GROUP BY mode").fetchall()
            return {str(r[0]): int(r[1]) for r in rows}

        return await self.database.read(read)
