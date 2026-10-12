"""Training the memory manager's layers (MEMORY_MANAGER_2026-10-08 §4). Run by hand:
``scripts/memory/train_layers.py``; the runbook is docs/runbooks/TRAINING_MEMORY_LAYERS.md.

Examples come from three places, each kept apart in the report:

1. **owner**: the manager's own decision log (features as Core computed them) joined with what
   the owner later did. A memory the owner deleted was not worth keeping. One the owner
   corrected was worth keeping, and the correction and the original are an "update" pair.
   A recall the answer used counts as worth keeping. A memory never recalled in 90 days is a
   weak "not worth keeping".
2. **files**: JSONL label files, written by the owner, by an agent from an export
   (``export_unlabelled``), or converted from a dataset. Text examples are embedded with the
   same embedder and features as Core uses.
3. **fabricated**: the probe's made-up examples, only when asked for, at low weight.

A layer is trained only with enough examples of both classes, is scored on a held-out split
(grouped, so paraphrases of one memory never straddle it), and is compared with the fixed
policy it would replace. It becomes active only when asked and only if it beats that policy.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sora.memory import features
from sora.memory.embedder import Embedder
from sora.memory.features import Thresholds
from sora.memory.layers import LayerSet, LogisticLayer, fit
from sora.memory.vectors import cosine, mean_vector, unpack

LAYERS = ("acceptance", "relevance", "same_subject", "update")
MIN_EXAMPLES = 40
MIN_PER_CLASS = 10
HELD_OUT = 0.2
ADOPT_MARGIN = 0.02  # held-out balanced accuracy must beat the fixed policy by this much
WEIGHTS = {"owner": 1.0, "files": 1.0, "fabricated": 0.3}


@dataclass
class Example:
    layer: str
    values: dict[str, float]
    label: int
    weight: float
    source: str  # owner | files | fabricated
    group: str  # held-out split key: examples sharing it stay on one side
    note: str = ""  # for the mistakes list (IDs or a short text)


@dataclass
class LayerReport:
    layer: str
    examples: int = 0
    positives: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    trainable: bool = False
    reason: str = ""
    trained: dict[str, float] = field(default_factory=dict)
    baseline: dict[str, float] = field(default_factory=dict)
    version: str = ""
    adopted: bool = False
    mistakes: list[str] = field(default_factory=list)


def baseline(layer: str, th: Thresholds) -> Callable[[Mapping[str, float]], bool]:
    """The fixed policy each layer replaces (as in sora.memory.manager)."""
    policies: dict[str, Callable[[Mapping[str, float]], bool]] = {
        "acceptance": lambda v: v.get("nominated", 1.0) >= 1,
        "relevance": lambda v: v["similarity_to_owner"] >= th.part_relevance,
        "same_subject": lambda v: v["similarity"] >= th.same_subject,
        "update": lambda v: bool(v["change_marker"] or v["number_mismatch"]
                                 or v["negation_mismatch"]),
    }
    return policies[layer]


# 1. Owner examples: decision log joined with the database.

def owner_examples(state_root: Path, database: Path, *, now: datetime | None = None
                   ) -> list[Example]:
    now = now or datetime.now(UTC)
    decisions = list(_read_jsonl((state_root / "memory" / "decisions").glob("*.jsonl")))
    if not decisions or not database.is_file():
        return []
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        memories = {row["memory_id"]: row for row in db.execute(
            "SELECT memory_id, content, deleted_at, superseded_by, created_at FROM memories")}
        try:
            similarity = {(r[0], r[1]): unpack(bytes(r[2])) for r in db.execute(
                "SELECT memory_id, embedder, vector FROM memory_vectors WHERE part='whole'")}
        except sqlite3.Error:
            similarity = {}
        try:
            used = {r[0] for r in db.execute(
                "SELECT DISTINCT memory_id FROM memory_recalls WHERE used=1")}
            recalled = {r[0] for r in db.execute("SELECT DISTINCT memory_id FROM memory_recalls")}
        except sqlite3.Error:
            used, recalled = set(), set()
    examples: list[Example] = []
    latest: dict[tuple[str, str, str | None], dict[str, Any]] = {}
    for record in decisions:  # the newest decision per (layer, memory, other) counts
        latest[(record["layer"], record["memory_id"], record.get("other_id"))] = record
    for (layer, memory_id, _other), record in latest.items():
        row = memories.get(memory_id)
        if row is None or layer != "acceptance":
            continue
        label, weight = None, WEIGHTS["owner"]
        created = _time(row["created_at"])
        if row["deleted_at"]:
            label = 0
        elif row["superseded_by"] or memory_id in used:
            label = 1
        elif created and now - created > timedelta(days=90) and memory_id not in recalled:
            label, weight = 0, 0.3
        if label is not None:
            examples.append(Example(layer, dict(record["features"]), label, weight, "owner",
                                    group=memory_id, note=memory_id))
    # Each owner correction is a same-subject update pair. The manager never compares them
    # itself (a corrected memory is superseded), so the pair is built from the stored
    # whole-memory vectors.
    for old_id, row in memories.items():
        new = memories.get(row["superseded_by"]) if row["superseded_by"] else None
        if new is None:
            continue
        for (vector_id, embedder), old_vector in similarity.items():
            new_vector = similarity.get((new["memory_id"], embedder))
            if vector_id != old_id or new_vector is None:
                continue
            old_time, new_time = _time(row["created_at"]), _time(new["created_at"])
            days = (abs((new_time - old_time).total_seconds()) / 86_400
                    if old_time and new_time else 0.0)
            values = features.comparison(new["content"], row["content"],
                                         cosine(new_vector, old_vector), days)
            for layer in ("same_subject", "update"):
                examples.append(Example(layer, values, 1, WEIGHTS["owner"], "owner",
                                        group=old_id,
                                        note=f"{new['memory_id']} corrects {old_id}"))
            break
    return examples


# 2./3. Label files: precomputed features, or text that is embedded here.

def file_examples(paths: Iterable[Path], source: str) -> list[dict[str, Any]]:
    """Raw label rows (validated, not yet embedded)."""
    rows = []
    for record in _read_jsonl(paths):
        if record.get("label") is None or record.get("layer") not in (*LAYERS, "comparison"):
            continue
        rows.append(dict(record, _source=source))
    return rows


async def embed_rows(rows: Sequence[Mapping[str, Any]], embedder: Embedder | None,
                     *, decisions: Mapping[str, Mapping[str, Any]]) -> list[Example]:
    """Turn label rows into examples, embedding text with Core's embedder and features."""
    th_personal: list[list[float]] = []
    th_chatter: list[list[float]] = []
    examples: list[Example] = []
    for row in rows:
        source = str(row["_source"])
        weight = float(row.get("weight", WEIGHTS[source]))
        layer = str(row["layer"])
        label = row["label"]
        if "decision_id" in row:  # an export the owner or an agent labelled
            decision = decisions.get(str(row["decision_id"]))
            if decision is None:
                continue
            examples.append(Example(str(decision["layer"]), dict(decision["features"]),
                                    int(label), weight, source, str(decision["memory_id"]),
                                    str(row["decision_id"])))
            continue
        if "features" in row:
            examples.append(Example(layer, {k: float(v) for k, v in row["features"].items()},
                                    int(label), weight, source, _group(row), _note(row)))
            continue
        if embedder is None:
            raise ValueError("text label rows need the embedder")
        if layer in ("comparison", "same_subject", "update"):
            a = await embedder.embed(str(row["a"]), "similarity")
            b = await embedder.embed(str(row["b"]), "similarity")
            values = features.comparison(str(row["b"]), str(row["a"]), cosine(a, b),
                                         float(row.get("days", 10)))
            kind = str(label)
            group = _group({"text": row["a"]})
            if layer in ("comparison", "same_subject"):
                examples.append(Example("same_subject", values,
                                        int(kind in ("same", "updated", "1", "True")),
                                        weight, source, group, _note(row)))
            if kind in ("same", "updated") and layer in ("comparison", "update"):
                examples.append(Example("update", values, int(kind == "updated"), weight,
                                        source, group, _note(row)))
            elif layer == "update" and kind in ("0", "1"):
                examples.append(Example("update", values, int(kind), weight, source, group,
                                        _note(row)))
        elif layer == "acceptance":
            if not th_personal:
                th_personal = [await embedder.embed(t, "similarity") for t in features.PERSONAL]
                th_chatter = [await embedder.embed(t, "similarity") for t in features.CHATTER]
            vector = await embedder.embed(str(row["text"]), "similarity")
            existing = [await embedder.embed(str(t), "similarity")
                        for t in row.get("existing", [])]
            values = features.acceptance(
                str(row["text"]),
                nearest_similarity=max((cosine(vector, e) for e in existing), default=0.0),
                similar_recent=0, personal=features.prototype_score(vector, th_personal),
                chatter=features.prototype_score(vector, th_chatter),
                nominated=bool(row.get("nominated", True)),
                own_thought=bool(row.get("own_thought", False)))
            examples.append(Example("acceptance", values, int(label), weight, source,
                                    _group(row), _note(row)))
        elif layer == "relevance":
            owner = await embedder.embed(str(row["owner"]), "similarity")
            part = await embedder.embed(str(row["part"]), "similarity")
            values = features.relevance(
                str(row.get("part_type", "reply")), similarity_to_owner=cosine(part, owner),
                similarity_to_entry=cosine(part, mean_vector([owner, part])),
                max_similarity_same_type=0.0, size=len(str(row["part"])))
            examples.append(Example("relevance", values, int(label), weight, source,
                                    _group({"text": row["owner"]}), _note(row)))
    return examples


# Training and reporting.

def count_layer(layer: str, examples: Sequence[Example], *, min_examples: int = MIN_EXAMPLES,
                min_per_class: int = MIN_PER_CLASS) -> LayerReport:
    """What is available for one layer, and whether it is enough to train (nothing is fitted)."""
    mine = [e for e in examples if e.layer == layer]
    report = LayerReport(layer, examples=len(mine), positives=sum(e.label for e in mine))
    for example in mine:
        report.by_source[example.source] = report.by_source.get(example.source, 0) + 1
    negatives = report.examples - report.positives
    if report.examples < min_examples or min(report.positives, negatives) < min_per_class:
        report.reason = (f"needs {min_examples}+ examples with {min_per_class}+ of each class; "
                         f"has {report.positives} yes / {negatives} no")
    else:
        report.trainable = True
    return report


def train_layer(layer: str, examples: Sequence[Example], *, th: Thresholds,
                min_examples: int = MIN_EXAMPLES, min_per_class: int = MIN_PER_CLASS,
                stamp: str = "") -> tuple[LayerReport, LogisticLayer | None]:
    report = count_layer(layer, examples, min_examples=min_examples,
                         min_per_class=min_per_class)
    if not report.trainable:
        return report, None
    report.trainable = False
    mine = [e for e in examples if e.layer == layer]
    held = [e for e in mine if _held_out(e.group)]
    train = [e for e in mine if not _held_out(e.group)]
    if not held or len({e.label for e in held}) < 2 or len({e.label for e in train}) < 2:
        report.reason = "the held-out split lacks one class; add more varied examples"
        return report, None
    report.trainable = True
    model = fit(layer, [(e.values, e.label, e.weight) for e in train], features.FEATURES[layer])
    threshold = _best_threshold(model, train)
    version = f"{layer}-{stamp or datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    model = LogisticLayer(**{**model.__dict__, "version": version, "threshold": threshold,
                             "trained_at": datetime.now(UTC).isoformat()})
    report.version = version
    report.trained = _score([model.decide(e.values) for e in held], held)
    policy = baseline(layer, th)
    report.baseline = _score([policy(e.values) for e in held], held)
    report.mistakes = [f"{e.note} (label {e.label}, p={model.probability(e.values):.2f})"
                       for e in held if model.decide(e.values) != bool(e.label)][:20]
    model = LogisticLayer(**{**model.__dict__, "metrics": {
        "held_out": report.trained, "baseline": report.baseline, "examples": report.examples,
        "by_source": report.by_source}})
    return report, model


def adopt(report: LayerReport, model: LogisticLayer, layers: LayerSet, *, activate: bool) -> Path:
    """Save the version; make it active only if asked and it beats the fixed policy."""
    better = (report.trained.get("balanced_accuracy", 0)
              >= report.baseline.get("balanced_accuracy", 0) + ADOPT_MARGIN)
    report.adopted = activate and better
    if activate and not better:
        report.reason = "kept as a candidate: not better than the fixed policy on held-out data"
    return layers.save(model, activate=report.adopted)


def export_unlabelled(state_root: Path, database: Path, target: Path,
                      *, labelled: set[str]) -> int:
    """Decisions with the memory texts, for the owner or an agent to label (set "label")."""
    decisions = list(_read_jsonl((state_root / "memory" / "decisions").glob("*.jsonl")))
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as db:
        texts = {r[0]: r[1] for r in db.execute("SELECT memory_id, content FROM memories "
                                                "WHERE deleted_at IS NULL")}
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("w", encoding="utf-8") as stream:
        for record in decisions:
            if record["id"] in labelled or record["memory_id"] not in texts:
                continue
            row = {"decision_id": record["id"], "layer": record["layer"],
                   "memory": texts[record["memory_id"]],
                   "other": texts.get(record.get("other_id") or ""),
                   "part": record.get("part"), "manager_decided": record["decision"],
                   "label": None,
                   "how_to_label": LABEL_HELP[record["layer"]]}
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


LABEL_HELP = {
    "acceptance": "1 if this is worth remembering about the owner long-term, else 0",
    "relevance": "1 if her reply belongs with this memory, else 0",
    "same_subject": "1 if both memories are about the same fact (a repeat or an update), else 0",
    "update": "1 if the newer memory replaces the older one, 0 if it only repeats it",
}


def report_markdown(reports: Sequence[LayerReport], *, trained: bool) -> str:
    lines = [f"# Memory layer training, {datetime.now():%Y-%m-%d %H:%M}", "",
             "Mode: " + ("trained" if trained else "check only (nothing trained)"), "",
             "| Layer | Examples (yes) | Sources | Trainable | Held-out balanced acc. "
             "| Fixed policy | Adopted |", "|---|---|---|---|---|---|---|"]
    for r in reports:
        lines.append(
            f"| {r.layer} | {r.examples} ({r.positives}) | "
            + ", ".join(f"{k} {v}" for k, v in sorted(r.by_source.items())) + " | "
            + ("yes" if r.trainable else "no: " + r.reason) + " | "
            + (f"{r.trained.get('balanced_accuracy', 0):.3f} (n={r.trained.get('held_out', 0):.0f})"
               if r.trained else "-") + " | "
            + (f"{r.baseline.get('balanced_accuracy', 0):.3f}" if r.baseline else "-") + " | "
            + ("yes" if r.adopted else (r.reason if r.version else "-")) + " |")
    for r in reports:
        if r.mistakes:
            lines += ["", f"## {r.layer}: held-out mistakes", ""] + [f"- {m}" for m in r.mistakes]
    return "\n".join(lines) + "\n"


def _score(predicted: Sequence[bool], examples: Sequence[Example]) -> dict[str, float]:
    tp = sum(p and e.label == 1 for p, e in zip(predicted, examples, strict=True))
    tn = sum(not p and e.label == 0 for p, e in zip(predicted, examples, strict=True))
    pos = sum(e.label for e in examples) or 1
    neg = (len(examples) - sum(e.label for e in examples)) or 1
    predicted_pos = sum(predicted) or 1
    return {"accuracy": round((tp + tn) / len(examples), 3),
            "balanced_accuracy": round((tp / pos + tn / neg) / 2, 3),
            "precision": round(tp / predicted_pos, 3), "recall": round(tp / pos, 3),
            "held_out": len(examples)}


def _best_threshold(model: LogisticLayer, train: Sequence[Example]) -> float:
    best, best_score = 0.5, -1.0
    for step in range(5, 96, 5):
        cut = step / 100
        predicted = [model.probability(e.values) >= cut for e in train]
        score = _score(predicted, train)["balanced_accuracy"]
        if score > best_score:
            best, best_score = cut, score
    return best


def _held_out(group: str) -> bool:
    return int(hashlib.sha256(group.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < HELD_OUT


def _group(row: Mapping[str, Any]) -> str:
    return str(row.get("group") or row.get("text") or row.get("a") or row.get("owner") or "")


def _note(row: Mapping[str, Any]) -> str:
    text = str(row.get("text") or row.get("a") or row.get("owner") or "")
    return text[:80] + (f" | {str(row.get('b') or row.get('part'))[:60]}"
                        if row.get("b") or row.get("part") else "")


def _time(value: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(value) if value else None
    except ValueError:
        return None


def _read_jsonl(paths: Iterable[Path]) -> Iterable[dict[str, Any]]:
    for path in sorted(paths):
        try:
            lines = path.read_text("utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.strip():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record


def decision_index(state_root: Path) -> dict[str, dict[str, Any]]:
    return {str(r["id"]): r for r in
            _read_jsonl((state_root / "memory" / "decisions").glob("*.jsonl")) if "id" in r}


def isfinite_examples(examples: Iterable[Example]) -> list[Example]:
    return [e for e in examples if all(math.isfinite(v) for v in e.values.values())]
