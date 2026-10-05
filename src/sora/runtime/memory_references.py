"""Turn-local canonical locators and factual retrieval evidence; never capture rationale."""

from __future__ import annotations

import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any

from sora.persistence.repository import SoraRepository
from sora.runtime.memory_browser import MemoryProjectionError, memory_page


def memory_presentation_requested(prompt: str) -> bool:
    owner = re.sub(r"```[\s\S]*?```|\"[^\"]*\"|(?<!\w)'[^'\n]*'(?!\w)|“[^”]*”|‘[^’]*’", " ", prompt)
    if re.search(
        r"\b(?:do not|don't|never|stop|without)\b[^.!?;]{0,100}"
        r"\b(?:show|open|inspect|highlight|display|bring)\b",
        owner,
        re.I,
    ):
        return False
    if re.search(
        r"\b(?:hypothetically|suppose|imagine|what if|what would|how (?:would|do|can)|"
        r"explain|describe|discuss)\b|\b(?:are you|can you)\s+(?:able|capable)\b",
        owner,
        re.I,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:show|open|inspect|highlight|display|bring)\b[^.!?;]{0,120}"
            r"\b(?:memor(?:y|ies)|remember(?:ed)?|preference|saved note)\b|"
            r"\bmemor(?:y|ies)\b[^.!?;]{0,80}\b(?:show|open|inspect|highlight|display)\b",
            owner,
            re.I,
        )
    )


@dataclass(frozen=True)
class MemoryTarget:
    memory_id: str
    version: int
    snippet: str


class MemoryReferences:
    def __init__(
        self,
        repository: SoraRepository,
        owner: str,
        project: str | None,
        instance: str,
        dialogue: str,
    ):
        self.repository, self.owner, self.project = repository, owner, project
        self.instance, self.dialogue = instance, dialogue
        self.nonce, self.cursor_key = uuid.uuid4().hex[:8], os.urandom(32)
        self.issued: dict[str, MemoryTarget] = {}
        self.compiled: set[str] = set()
        self.exposed: set[str] = set()
        self.cursors: dict[str, tuple[str, str]] = {}
        self.started = time.monotonic()
        self.published: set[tuple[str, tuple[tuple[str, int], ...]]] = set()

    def issue(self, memory_id: str, version: int, snippet: str) -> str | None:
        for reference, target in self.issued.items():
            if (target.memory_id, target.version) == (memory_id, version):
                return reference
        if len(self.issued) >= 64:
            return None
        reference = f"m{self.nonce}-r{len(self.issued) + 1}"
        self.issued[reference] = MemoryTarget(memory_id, version, snippet[:300])
        return reference

    def preview(self) -> dict[str, Any]:
        return {
            "memories": [
                {"target": ref, "text": target.snippet}
                for ref, target in self.issued.items()
                if ref in self.compiled
            ]
        }

    def expose(self, records: list[dict[str, Any]]) -> set[str]:
        supplied: set[str] = set()
        for record in records:
            if record.get("operation") not in {"memory_context", "find_memory"}:
                continue
            for item in record.get("data", {}).get("memories", []):
                if isinstance(item, dict) and item.get("target") in self.issued:
                    self.exposed.add(item["target"])
                    supplied.add(item["target"])
        return supplied

    def resolve(self, reference: str) -> MemoryTarget:
        if time.monotonic() - self.started >= 60:
            raise ValueError("Memory reference expired; retrieve again")
        if reference not in self.exposed or reference not in self.issued:
            raise ValueError("Unknown or unexposed canonical Memory reference")
        return self.issued[reference]

    async def find(self, query: str, cursor: str | None) -> dict[str, Any]:
        if time.monotonic() - self.started >= 60:
            raise ValueError("Memory lookup expired")
        saved = self.cursors.get(cursor) if cursor is not None else None
        if cursor is not None and (saved is None or saved[0] != query):
            raise ValueError("Memory cursor does not match the issued query")
        try:
            page = await self.repository.database.read(
                lambda db: memory_page(
                    db,
                    owner=self.owner,
                    project_id=self.project,
                    instance=self.instance,
                    key=self.cursor_key,
                    query=query,
                    state="active",
                    project="all",
                    scope="",
                    limit=10,
                    cursor=saved[1] if saved else None,
                )
            )
        except (MemoryProjectionError, sqlite3.Error) as exc:
            raise ValueError("Canonical Memory lookup unavailable; no records supplied") from exc
        items: list[dict[str, str]] = []
        for memory in page.memories:
            if memory.retention != "durable" or memory.sensitivity == "secret":
                continue
            reference = self.issue(memory.memory_id, memory.entity_version, memory.content_preview)
            if reference is not None:
                items.append({"target": reference, "text": memory.content_preview})
        continuation = None
        if page.next_cursor is not None and len(self.cursors) < 6 and len(self.issued) < 64:
            continuation = f"m{self.nonce}-p{len(self.cursors) + 1}"
            self.cursors[continuation] = (query, page.next_cursor)
        return {
            "memories": items,
            "continuation": continuation,
            "note": "Literal canonical content lookup; no semantic ranking or private captures.",
        }

    async def publish(self, stage: str, references: set[str]) -> None:
        targets = sorted(
            {
                (self.issued[ref].memory_id, self.issued[ref].version)
                for ref in references
                if ref in self.issued
            }
        )
        key = (stage, tuple(targets))
        if not targets or key in self.published:
            return
        retrieval = "retrieval-" + str(uuid.uuid4())

        def write(db: sqlite3.Connection) -> None:
            revision = int(
                db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
            )
            self.repository._append_event(
                db,
                self.owner,
                revision,
                "memory.retrieved",
                None,
                None,
                {
                    "retrieval_id": retrieval,
                    "dialogue_request_id": self.dialogue,
                    "instance_id": self.instance,
                    "stage": stage,
                    "source": "canonical",
                    "memories": [
                        {"memory_id": memory_id, "entity_version": version}
                        for memory_id, version in targets
                    ],
                },
            )

        await self.repository.database.write(write)
        self.published.add(key)
