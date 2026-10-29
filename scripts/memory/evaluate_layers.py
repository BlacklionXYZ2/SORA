"""Score trained memory layers against their fixed policies on test label files.

    uv run python scripts/memory/evaluate_layers.py --state-root <state> --tests <folder>

Test files use the same JSONL format as training labels (``convert_datasets.py`` writes
LongMemEval ones). They are embedded with Core's embedder and features, then each layer's
newest saved version (or ``--version layer=version``) and its fixed policy are scored on them.
Nothing is trained or activated. A test set with one class only (for example, LongMemEval has
real updates but no repeats) reports recall for it, and balanced accuracy is left out.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from sora.memory import training
from sora.memory.embedder import EmbedderConfig, LlamaEmbedder
from sora.memory.features import Thresholds
from sora.memory.layers import LayerSet, LogisticLayer
from sora.memory.settings import DEFAULT_MODEL, DEFAULT_SERVER

ROOT = Path(__file__).resolve().parents[2]


def score(predicted: Sequence[bool], labels: Sequence[int]) -> dict[str, float]:
    positives = sum(labels)
    negatives = len(labels) - positives
    tp = sum(p and y == 1 for p, y in zip(predicted, labels, strict=True))
    tn = sum(not p and y == 0 for p, y in zip(predicted, labels, strict=True))
    result: dict[str, float] = {"examples": len(labels),
                                "accuracy": round((tp + tn) / len(labels), 3)}
    if positives:
        result["recall"] = round(tp / positives, 3)
    if negatives:
        result["specificity"] = round(tn / negatives, 3)
    if positives and negatives:
        result["balanced_accuracy"] = round((tp / positives + tn / negatives) / 2, 3)
    return result


async def main_async(args: argparse.Namespace) -> int:
    rows = training.file_examples(sorted(Path(args.tests).glob("*.jsonl")), "files")
    embedder = LlamaEmbedder(EmbedderConfig(
        server=ROOT / DEFAULT_SERVER, model=ROOT / DEFAULT_MODEL, port=18931,
        gpu_layers="0" if args.cpu else "99",
        log=args.state_root / "logs" / "memory-evaluation.log"))
    try:
        examples = training.isfinite_examples(
            await training.embed_rows(rows, embedder, decisions={}))
    finally:
        await embedder.close()
    chosen = dict(item.split("=", 1) for item in args.version)
    layers = LayerSet(args.state_root / "memory" / "layers")
    th = Thresholds()
    results = {}
    for name in training.LAYERS:
        mine = [e for e in examples if e.layer == name]
        versions = layers.versions(name)
        if not mine or not versions:
            continue
        version = chosen.get(name, versions[-1])
        model = LogisticLayer.from_json(
            (layers.root / name / f"{version}.json").read_text("utf-8"))
        labels = [e.label for e in mine]
        policy = training.baseline(name, th)
        results[name] = {"version": version,
                         "trained": score([model.decide(e.values) for e in mine], labels),
                         "fixed policy": score([policy(e.values) for e in mine], labels)}
    for name, result in results.items():
        print(f"{name} ({result['version']}):")
        for kind in ("trained", "fixed policy"):
            print(f"  {kind:12} " + ", ".join(f"{k} {v}" for k, v in result[kind].items()))
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding="utf-8")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True, help="folder of test label files")
    parser.add_argument("--version", nargs="*", default=[], metavar="LAYER=VERSION",
                        help="score these versions instead of the newest saved ones")
    parser.add_argument("--json", type=Path, help="also write the results here")
    parser.add_argument("--cpu", action="store_true", help="embed on the CPU")
    raise SystemExit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
