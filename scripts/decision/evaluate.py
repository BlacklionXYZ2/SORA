"""Score a Laya GGUF on labelled messages, the way SORA uses it.

    uv run python scripts/decision/evaluate.py training/decision/seed_eval.jsonl
    uv run python scripts/decision/evaluate.py my_eval.jsonl ^
        --model .local/decision/trained/laya_sora_q8_0.gguf

For each threshold it reports, per family and overall:
  recall     -- of the families a message needed, how many were offered (missing = she can't);
  precision  -- of the families offered, how many were needed (extra = more for the brain to pick);
  complete   -- messages where every needed family was offered (the number that matters most);
  offered    -- average families offered (lower = a simpler choice for the brain).
A JSON report is written next to the data unless --report is given.
See docs/runbooks/TRAINING_LAYA.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sora.decision.dataset import load_catalogue, read_examples  # noqa: E402
from sora.decision.families import FAMILIES  # noqa: E402
from sora.decision.laya import LayaDecisionLayer  # noqa: E402
from sora.decision.settings import DEFAULT_MODEL, DEFAULT_RUNNER  # noqa: E402

THRESHOLDS = (0.5, 0.35, 0.25, 0.15)
AGENTS = ("Cody", "Hermes", "Aggie", "Claude", "Pip")


async def score(data: Path, model: Path, runner: Path, device: str) -> dict[str, object]:
    catalogue = load_catalogue()
    examples = read_examples(data, catalogue)
    # SORA's own families, plus any extension family the data is labelled with (for the
    # held-out set, families the model never saw in training).
    labelled = sorted({name for e in examples for name in e.families} - {f.name for f in FAMILIES})
    families = (*FAMILIES, *(catalogue.families[name] for name in labelled))
    layer = LayaDecisionLayer(runner, model, device=device, timeout=30, families=families)
    probabilities: list[dict[str, float]] = []
    latencies: list[float] = []
    try:
        for example in examples:
            decision = await layer.decide(example.message, threshold=0.5, agent_names=AGENTS)
            if decision is None:
                raise SystemExit(f"The runner failed: {layer.state} {layer.reason}")
            probabilities.append(decision.probabilities)
            latencies.append(decision.latency_ms)
    finally:
        await layer.close()
    results: dict[str, object] = {}
    for threshold in THRESHOLDS:
        per_family = {}
        for family in families:
            tp = fp = fn = 0
            for example, probs in zip(examples, probabilities, strict=True):
                shown, wanted = probs[family.name] >= threshold, family.name in example.families
                tp += shown and wanted
                fp += shown and not wanted
                fn += wanted and not shown
            per_family[family.name] = {
                "recall": round(tp / (tp + fn), 3) if tp + fn else None,
                "precision": round(tp / (tp + fp), 3) if tp + fp else None,
                "needed": tp + fn,
            }
        offered_sets = [{n for n, p in probs.items() if p >= threshold} for probs in probabilities]
        tp = sum(len(o & e.families) for o, e in zip(offered_sets, examples, strict=True))
        needed = sum(len(e.families) for e in examples)
        offered = sum(len(o) for o in offered_sets)
        results[str(threshold)] = {
            "recall": round(tp / needed, 3) if needed else None,
            "precision": round(tp / offered, 3) if offered else None,
            "complete": sum(e.families <= o for o, e in zip(offered_sets, examples, strict=True)),
            "offered": round(offered / len(examples), 2),
            "families": per_family,
            "missed": [e.message for o, e in zip(offered_sets, examples, strict=True)
                       if not e.families <= o][:20],
        }
    latencies.sort()
    return {
        "data": str(data), "model": str(model), "messages": len(examples),
        "families_asked": [f.name for f in families],
        "median_ms": round(latencies[len(latencies) // 2], 1), "max_ms": round(latencies[-1], 1),
        "thresholds": results, "evaluated_at": datetime.now().isoformat(timespec="seconds"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("data", type=Path, help="labelled JSONL (message, families, source)")
    parser.add_argument("--model", type=Path, default=ROOT / DEFAULT_MODEL)
    parser.add_argument("--runner", type=Path, default=ROOT / DEFAULT_RUNNER)
    parser.add_argument("--device", default="auto", choices=("auto", "vulkan", "cpu"))
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    report = asyncio.run(score(args.data, args.model, args.runner, args.device))
    print(f"{report['messages']} messages, {report['model']}")
    print(f"latency: median {report['median_ms']} ms, max {report['max_ms']} ms")
    print(f"{'threshold':>9} {'recall':>7} {'precision':>9} {'complete':>9} {'offered':>8}")
    thresholds = cast("dict[str, dict[str, Any]]", report["thresholds"])
    asked = len(cast("list[str]", report["families_asked"]))
    for threshold, row in thresholds.items():
        print(f"{threshold:>9} {row['recall']!s:>7} {row['precision']!s:>9} "
              f"{row['complete']:>4}/{report['messages']:<4} {row['offered']:>6}/{asked}")
    target = args.report or args.data.with_suffix(f".report-{Path(args.model).stem}.json")
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"report: {target}")


if __name__ == "__main__":
    main()
