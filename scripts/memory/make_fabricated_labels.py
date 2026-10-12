"""Turn the probes' fabricated cases into label files for the memory layers.

    uv run python scripts/memory/make_fabricated_labels.py

Writes training/memory/labels/fabricated/probe_labels.jsonl from embedder_probe.json and
use_case_probe.json. These are made-up examples, used only with
``train_layers.py --include-fabricated`` and at low weight: enough to exercise training, not to
shape her memory. Real labels come from the owner (see docs/runbooks/TRAINING_MEMORY_LAYERS.md).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    base = json.loads((ROOT / "training/memory/embedder_probe.json").read_text("utf-8"))
    cases = json.loads((ROOT / "training/memory/use_case_probe.json").read_text("utf-8"))
    corpus = [m["text"] for m in base["memories"]]
    text = {m["id"]: m["text"] for m in base["memories"]}
    rows: list[dict[str, Any]] = []
    for pair in base["pairs"]:
        rows.append({"layer": "comparison", "a": pair["a"], "b": pair["b"],
                     "label": pair["label"], "days": 10})
    for pair in cases["pairs_extra"]:
        rows.append({"layer": "comparison", "a": pair["a"], "b": pair["b"],
                     "label": pair["label"], "days": pair["days"]})
    for line in cases["worth"]:
        rows.append({"layer": "acceptance", "text": line, "label": 1, "existing": corpus})
    for line in cases["chatter"]:
        rows.append({"layer": "acceptance", "text": line, "label": 0, "existing": corpus})
    for repeat in cases["repeats"]:  # already remembered: not worth a second memory
        rows.append({"layer": "acceptance", "text": repeat["text"], "label": 0,
                     "existing": corpus, "group": text[repeat["id"]]})
    for thought in cases["own_thoughts"]:
        rows.append({"layer": "acceptance", "text": thought["thought"], "label": 1,
                     "own_thought": True, "existing": corpus})
    for entry in cases["parts"]:
        for part in entry["relevant"]:
            rows.append({"layer": "relevance", "owner": entry["owner"], "part": part,
                         "part_type": "read" if ":" in part[:30] else "reply", "label": 1})
        for part in entry["irrelevant"]:
            rows.append({"layer": "relevance", "owner": entry["owner"], "part": part,
                         "part_type": "read" if ":" in part[:30] else "reply", "label": 0})
    target = ROOT / "training/memory/labels/fabricated/probe_labels.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps({**row, "source_note": "fabricated by Opus 5.5, 2026-10-09"},
                                    ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows: {target}")


if __name__ == "__main__":
    main()
