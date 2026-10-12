"""Multimodal memories: how should a text + image + audio memory be stored for recall?

    uv run python scripts/memory/probe_multimodal.py

Each fabricated memory (training/memory/multimodal_probe.json) has text, an image and a spoken
note that says something new. Questions aim at one part only. Four ways of storing a memory
are compared, against the 30 text-only memories of embedder_probe.json as distractors:

  fused     one embedding of text + image + audio together (interleaved input);
  text      the text alone (what SORA stores today);
  max-part  one vector per part, scored by the closest part;
  mean-part the average of the part vectors.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("probe_embedder",
                                               ROOT / "scripts/memory/probe_embedder.py")
assert _spec is not None and _spec.loader is not None
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

QUERY = "task: search result | query: {}"
DOC = "title: none | text: {}"


def resolve(ref: str) -> Path:
    return probe.SCRATCH / ref.removeprefix("scratch:") if ref.startswith("scratch:") \
        else ROOT / ref


def main() -> None:
    data = json.loads((ROOT / "training/memory/multimodal_probe.json").read_text("utf-8"))
    distractors = json.loads(
        (ROOT / "training/memory/embedder_probe.json").read_text("utf-8"))["memories"]
    memories = data["memories"]
    models = ROOT / ".local/models/embeddinggemma-2"
    embed = probe.Embedder(ROOT / ".local/llama.cpp-b11516/llama-server.exe",
                           models / "embeddinggemma-2-UD-Q4_K_XL.gguf",
                           models / "mmproj-Q8_0.gguf", "99")
    report: dict[str, Any] = {"memories": len(memories), "distractors": len(distractors)}
    try:
        notes = probe.speak({m["id"] + "-note": m["audio"] for m in memories})
        parts: dict[str, dict[str, list[float]]] = {}
        fused: dict[str, list[float]] = {}
        for memory in memories:
            image, audio = resolve(memory["image"]), notes[memory["id"] + "-note"]
            parts[memory["id"]] = {
                "text": embed.text(DOC.format(memory["text"])),
                "image": embed.media(image, "image"),
                "audio": embed.media(audio, "audio"),
            }
            m = embed.marker
            content = [{
                "prompt_string": DOC.format(memory["text"]) + f" {m} {m}",
                "multimodal_data": [base64.b64encode(image.read_bytes()).decode(),
                                    base64.b64encode(audio.read_bytes()).decode()],
            }]
            fused[memory["id"]] = embed._embed(content, "image")
        others = [embed.text(DOC.format(d["text"])) for d in distractors]

        def mean_vector(vectors: list[list[float]]) -> list[float]:
            return probe.unit([sum(column) / len(column) for column in zip(*vectors,
                                                                           strict=True)])

        strategies = {
            "fused": lambda q, mid: probe.cos(q, fused[mid]),
            "text": lambda q, mid: probe.cos(q, parts[mid]["text"]),
            "max-part": lambda q, mid: max(probe.cos(q, v) for v in parts[mid].values()),
            "mean-part": lambda q, mid: probe.cos(q, mean_vector(list(parts[mid].values()))),
        }
        results: dict[str, dict[str, Any]] = {}
        for kind in ("text", "image_only", "audio_only"):
            asked = [(m["id"], m["questions"][kind]) for m in memories if m["questions"][kind]]
            vectors = [(mid, embed.text(QUERY.format(q))) for mid, q in asked]
            for name, score in strategies.items():
                found = []
                for target, query in vectors:
                    mine = score(query, target)
                    rivals = [score(query, m["id"]) for m in memories if m["id"] != target]
                    rivals += [probe.cos(query, o) for o in others]
                    found.append(1 + sum(1 for r in rivals if r > mine))
                results.setdefault(name, {})[kind] = {
                    **probe.summary(found), "ranks": dict(zip([a for a, _ in asked], found,
                                                              strict=True))}
        report["recall"] = results
        report["fused_vs_parts"] = {
            m["id"]: {part: round(probe.cos(fused[m["id"]], v), 3)
                      for part, v in parts[m["id"]].items()} for m in memories}
        report["speed_ms"] = {k: round(mean(v[1:] or v), 1) for k, v in embed.times.items() if v}
    finally:
        embed.close()
    target = probe.OUT / f"multimodal-{datetime.now():%Y%m%d-%H%M%S}.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{'strategy':10} {'question aims at':12} rank1  top3  mrr")
    for name, kinds in report["recall"].items():
        for kind, r in kinds.items():
            print(f"{name:10} {kind:12} {r['rank1']:.2f}  {r['top3']:.2f}  {r['mrr']:.2f}")
    print("fused vector's similarity to each part (mean):",
          {p: round(mean(v[p] for v in report["fused_vs_parts"].values()), 3)
           for p in ("text", "image", "audio")})
    print("report:", target)


if __name__ == "__main__":
    main()
