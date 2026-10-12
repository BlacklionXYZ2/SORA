"""Memory manager pipeline and training program, with a deterministic fake embedder.

The real embedder (EmbeddingGemma 2) is exercised by scripts/memory/probe_use_cases.py; these
tests pin the plumbing: vectors, links, decision logs, recall, shadow/on selection, layers,
training examples, adoption and rollback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import pytest

from sora.memory import features, training
from sora.memory.features import Thresholds
from sora.memory.layers import LayerSet, LogisticLayer, fit
from sora.memory.manager import DecisionLog, MemoryManager
from sora.memory.settings import MemoryManagerSettings
from sora.memory.store import MemoryVectorStore
from sora.memory.vectors import pack, project, top_k, unit, unpack
from sora.providers.mock import DeterministicProvider
from sora.runtime.memory_host import MemoryHost
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]
LOOSE = Thresholds(related=0.3, same_subject=0.5, part_relevance=0.3, recall_floor=0.2,
                   image_relevance=0.3, audio_relevance=0.3)


class FakeEmbedder:
    """Bag-of-words vectors: texts sharing words are similar, so outcomes are predictable."""

    identity = "fake@1024"
    dims = 1024

    def __init__(self) -> None:
        self.calls = 0

    async def embed(self, text: str, role: Literal["query", "document", "similarity"],
                    *, title: str = "none") -> list[float]:
        self.calls += 1
        vector = [0.0] * self.dims
        for word in features.words(text) or {"empty"}:
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % self.dims] += 1.0
        return unit(vector)

    modalities = frozenset({"text", "image", "audio"})

    async def embed_media(self, data: bytes, kind: Literal["image", "audio"]) -> list[float]:
        """Media looks like the words "desk monitors" plus its kind, so it is predictable."""
        return await self.embed(f"desk monitors {kind} {len(data) % 3}", "document")

    async def embed_mixed(self, text: str, role: Literal["query", "document", "similarity"],
                          media: Sequence[bytes]) -> list[float]:
        return await self.embed(text + " desk monitors" * bool(media), role)

    async def close(self) -> None:
        pass


async def runtime(tmp_path: Path) -> SoraRuntime:
    instance = SoraRuntime(RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
                           provider=DeterministicProvider())
    await instance.start()
    return instance


async def remember(instance: SoraRuntime, memory_id: str, content: str) -> None:
    await instance.repository.add_memory(
        memory_id=memory_id, owner_id=instance.config.owner_id,
        project_id=instance.config.project_id, content=content, scope="dialogue",
        sensitivity="private", retention="durable", provenance="owner-stated (test)")


def manager_for(instance: SoraRuntime, tmp_path: Path, embedder: FakeEmbedder) -> MemoryManager:
    return MemoryManager(
        repository=instance.repository, store=MemoryVectorStore(instance.repository.database),
        embedder=embedder, layers=LayerSet(tmp_path / "memory/layers"),
        log=DecisionLog(tmp_path / "memory/decisions"), owner_id=instance.config.owner_id,
        project_id=instance.config.project_id, captures_root=tmp_path / "captures",
        thresholds=LOOSE)


def test_vectors_round_trip_rank_and_project() -> None:
    v = unit([3.0, 4.0, 0.0])
    assert unpack(pack(v)) == pytest.approx(v, abs=1e-6)
    items = [("a", unit([1, 0, 0])), ("b", unit([1, 1, 0])), ("a", unit([0.9, 0.1, 0]))]
    assert [k for k, _ in top_k(unit([1, 0, 0]), items, k=5)] == ["a", "b"]
    assert top_k(unit([1, 0, 0]), items, k=5, floor=0.9, exclude=frozenset({"a"})) == []
    points = project([unit([1, 0, 0]), unit([0, 1, 0]), unit([0, 0, 1]), unit([1, 1, 0])], 2)
    assert len(points) == 4 and all(len(p) == 2 for p in points)
    assert points == project([unit([1, 0, 0]), unit([0, 1, 0]), unit([0, 0, 1]),
                              unit([1, 1, 0])], 2)  # repeatable


def test_comparison_and_acceptance_features() -> None:
    values = features.comparison("My favourite colour is now green.",
                                 "My favourite colour is teal.", 0.9, 30)
    assert values["change_marker"] == 1 and values["token_jaccard"] > 0.3
    assert features.comparison("Exams start on the 20th", "Exams start on the 14th", 0.9,
                               1)["number_mismatch"] == 1
    assert features.acceptance("Where is my key?", nearest_similarity=0.5, similar_recent=9,
                               personal=0.6, chatter=0.4)["is_question"] == 1
    assert set(features.relevance("image", similarity_to_owner=0.7, similarity_to_entry=0.8,
                                  max_similarity_same_type=0, size=10)) == set(
        features.RELEVANCE)


def test_layers_fit_save_activate_and_roll_back(tmp_path: Path) -> None:
    examples = [({"similarity": s, "token_jaccard": 0.0}, int(s > 0.8), 1.0)
                for s in (0.5, 0.6, 0.7, 0.75, 0.85, 0.9, 0.95, 0.99)]
    layer = fit("same_subject", examples, features.COMPARISON)
    assert layer.decide({"similarity": 0.97}) and not layer.decide({"similarity": 0.55})
    layers = LayerSet(tmp_path)
    for version in ("v1", "v2"):
        layers.save(LogisticLayer(**{**layer.__dict__, "version": version}), activate=True)
    assert layers.policy("same_subject") == "layer:v2"
    layers.activate("same_subject", "v1")  # rollback
    assert LayerSet(tmp_path).policy("same_subject") == "layer:v1"
    bad = json.loads(layer.to_json()) | {"features": ["invented"], "means": [0], "scales": [1],
                                         "weights": [1]}
    with pytest.raises(ValueError, match="no longer computes"):
        LogisticLayer.from_json(json.dumps(bad))


@pytest.mark.asyncio
async def test_manager_embeds_links_and_logs_without_changing_memories(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    try:
        await remember(instance, "memory-colour", "My favourite colour is teal")
        await remember(instance, "memory-colour-new", "My favourite colour is now green")
        await remember(instance, "memory-bike", "My bike tyre has a slow puncture")
        embedder = FakeEmbedder()
        manager = manager_for(instance, tmp_path, embedder)
        run = await manager.run()
        assert run.embedded == 3 and run.remaining == 0
        assert (await manager.run()).embedded == 0  # nothing left to do
        links = await manager.store.links("memory-colour-new")
        kinds = {(link.kind, link.target_id) for link in links}
        assert ("same_subject", "memory-colour") in kinds
        assert ("update", "memory-colour") in kinds  # "now" marks an update
        logged = [json.loads(line) for f in (tmp_path / "memory/decisions").glob("*.jsonl")
                  for line in f.read_text("utf-8").splitlines()]
        assert {r["layer"] for r in logged} >= {"acceptance", "same_subject", "update"}
        assert all("content" not in json.dumps(r) and "teal" not in json.dumps(r)
                   for r in logged)  # IDs and features only, never memory text
        memories = await instance.repository.list_memories(
            instance.config.owner_id, project_id=instance.config.project_id,
            observed_at=datetime.now(UTC))
        assert len(memories) == 3  # the manager never withdraws or supersedes on its own
        ranked = await manager.recall("what colour do I like", memories)
        assert ranked and ranked[0].memory_id.startswith("memory-colour")
        assert "memory-bike" not in {r.memory_id for r in ranked}
        positions = await manager.map_coordinates()  # from the whole-memory vectors
        assert set(positions) == {"memory-colour", "memory-colour-new", "memory-bike"}
        assert all(len(p) == 2 for p in positions.values())
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_host_shadow_keeps_recency_and_on_puts_relevant_first(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    try:
        for index, text in enumerate(["My sister Ada hates surprises", "Our cat Miso is twelve",
                                      "My bike tyre is flat", "Always answer briefly"]):
            await remember(instance, f"memory-{index}", text)
        mode: list[Literal["off", "shadow", "on"]] = ["shadow"]
        traces: list[tuple[str, dict[str, object]]] = []

        async def trace(correlation: str, phase: str, fields: dict[str, object]) -> None:
            traces.append((phase, fields))

        host = MemoryHost(repository=instance.repository, state_root=tmp_path,
                          owner_id=instance.config.owner_id,
                          project_id=instance.config.project_id,
                          captures_root=tmp_path / "captures", trace=trace,
                          settings=lambda: MemoryManagerSettings(mode=mode[0]))
        host.enabled = True
        manager = manager_for(instance, tmp_path, FakeEmbedder())
        host._manager = lambda: manager  # type: ignore[method-assign]
        host.store = manager.store
        await manager.run()
        memories = await instance.repository.list_memories(
            instance.config.owner_id, project_id=instance.config.project_id,
            observed_at=datetime.now(UTC))
        recent = memories[-2:]
        chosen = await host.select("is the cat okay", recent, memories, limit=2,
                                   correlation_id="turn-1")
        # shadow: memories sharing words with the message, then the newest (no embedder use)
        assert [m.memory_id for m in chosen] == ["memory-1", "memory-3"]
        await asyncio.gather(*host._tasks)
        counts = await host.store.recall_counts()
        assert counts.get("shadow", 0) >= 1 and counts.get("recency") == 2
        assert traces and traces[-1][0] == "memory.recall"
        mode[0] = "on"
        chosen = await host.select("is the cat okay", recent, memories, limit=2,
                                   correlation_id="turn-2")
        assert chosen[0].memory_id == "memory-1"  # the cat, though it isn't recent
        assert chosen[1].memory_id == "memory-3"  # the newest fills the remaining place
        again = await host.select("something else", recent, memories, limit=2,
                                  correlation_id="turn-2")
        assert again == chosen  # the same turn rebuilding its context
        await host.close()
    finally:
        await instance.close()


@pytest.mark.asyncio
async def test_training_examples_from_owner_actions_and_files(tmp_path: Path) -> None:
    instance = await runtime(tmp_path)
    try:
        await remember(instance, "memory-keep", "My exams start on the 14th of May")
        await remember(instance, "memory-drop", "lol okay")
        embedder = FakeEmbedder()
        await manager_for(instance, tmp_path, embedder).run()
        await instance.repository.delete_memory("memory-drop", deleted_at=datetime.now(UTC))
        await instance.repository.correct_memory(
            "memory-keep", replacement_id="memory-fixed",
            content="My exams start on the 20th of May", provenance="owner-corrected (test)")
        await manager_for(instance, tmp_path, embedder).run()
        database = tmp_path / "data" / "sora.db"
        examples = training.owner_examples(tmp_path, database,
                                           now=datetime.now(UTC) + timedelta(days=1))
        acceptance = {e.note: e.label for e in examples if e.layer == "acceptance"}
        assert acceptance.get("memory-drop") == 0  # the owner deleted it
        assert acceptance.get("memory-keep") == 1  # the owner corrected it
        pairs = {(e.layer, e.label) for e in examples if "corrects" in e.note}
        assert pairs == {("same_subject", 1), ("update", 1)}
        target = tmp_path / "export.jsonl"
        assert training.export_unlabelled(tmp_path, database, target, labelled=set()) >= 1
        exported = [json.loads(line) for line in target.read_text("utf-8").splitlines()]
        assert all(row["label"] is None and row["how_to_label"] for row in exported)
        rows = training.file_examples(
            [ROOT / "training/memory/labels/fabricated/probe_labels.jsonl"], "fabricated")
        assert {r["layer"] for r in rows} == {"comparison", "acceptance", "relevance"}
        made = await training.embed_rows(rows[:6], embedder, decisions={})
        assert {e.layer for e in made} >= {"same_subject"}
        assert all(math.isfinite(v) for e in made for v in e.values.values())
    finally:
        await instance.close()


def test_training_only_adopts_a_layer_that_beats_the_fixed_policy(tmp_path: Path) -> None:
    def example(similarity: float, label: int, group: str) -> training.Example:
        values = features.comparison("a b c", "a b d", similarity, 1)
        return training.Example("same_subject", values, label, 1.0, "files", group)

    few = [example(0.9, 1, "g1")]
    report = training.count_layer("same_subject", few)
    assert not report.trainable and "needs 40+" in report.reason
    # The fixed policy (similarity >= 0.85) is already perfect here, so nothing is adopted.
    data = [example(0.86 + i / 1000, 1, f"p{i}") for i in range(30)] + \
           [example(0.70 + i / 1000, 0, f"n{i}") for i in range(30)]
    report, model = training.train_layer("same_subject", data, th=Thresholds())
    assert model is not None and report.trained and report.baseline
    layers = LayerSet(tmp_path)
    training.adopt(report, model, layers, activate=True)
    assert not report.adopted and layers.policy("same_subject") == "fixed-threshold"
    assert layers.versions("same_subject") == [model.version]  # kept as a candidate
