"""Train the memory manager's layers, or check whether there is enough to train them.

    uv run python scripts/memory/train_layers.py                 # check only (the default)
    uv run python scripts/memory/train_layers.py --train         # train; save candidates
    uv run python scripts/memory/train_layers.py --train --adopt # make better ones active
    uv run python scripts/memory/train_layers.py --export-unlabelled .local/memory-labels.jsonl
    uv run python scripts/memory/train_layers.py --list
    uv run python scripts/memory/train_layers.py --rollback update update-20261101T120000

Reads the profile's decision log and database read-only (the running SORA can stay open), plus
label files from training/memory/labels/*.jsonl and <state>/memory/labels/*.jsonl. Text labels
are embedded with a temporary embedding server (Core's own class and features). Layer versions
and reports go to <state>/memory/layers/. A running SORA picks up an adopted layer on the
memory manager's next run. Guide: docs/runbooks/TRAINING_MEMORY_LAYERS.md.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from sora.memory import training
from sora.memory.embedder import EmbedderConfig, LlamaEmbedder
from sora.memory.features import Thresholds
from sora.memory.layers import LayerSet, LogisticLayer
from sora.memory.settings import DEFAULT_MODEL, DEFAULT_SERVER

ROOT = Path(__file__).resolve().parents[2]


async def gather(args: argparse.Namespace, *, embed: bool) -> list[training.Example]:
    state: Path = args.state_root
    examples = training.owner_examples(state, args.database)
    sources = [(sorted((ROOT / "training/memory/labels").glob("*.jsonl")), "files"),
               (sorted((state / "memory/labels").glob("*.jsonl")), "files")]
    sources += [(sorted(Path(d).glob("*.jsonl")), "files") for d in args.labels]
    if args.include_fabricated:
        sources.append((sorted((ROOT / "training/memory/labels/fabricated").glob("*.jsonl")),
                        "fabricated"))
    rows = [row for paths, source in sources for row in training.file_examples(paths, source)]
    decisions = training.decision_index(state)
    needs_text = [r for r in rows if "decision_id" not in r and "features" not in r]
    if needs_text and not embed:
        # Check mode: count text rows by the layer(s) they will feed, without embedding.
        for row in needs_text:
            label, source = str(row["label"]), str(row["_source"])
            if row["layer"] == "comparison":
                examples.append(training.Example("same_subject", {}, int(
                    label in ("same", "updated")), 1.0, source, "", ""))
                if label in ("same", "updated"):
                    examples.append(training.Example("update", {}, int(label == "updated"),
                                                     1.0, source, "", ""))
            else:
                examples.append(training.Example(str(row["layer"]), {},
                                                 int(label in ("1", "True")), 1.0, source,
                                                 "", ""))
        rows = [r for r in rows if r not in needs_text]
        return examples + await training.embed_rows(rows, None, decisions=decisions)
    embedder = None
    if needs_text:
        embedder = LlamaEmbedder(EmbedderConfig(
            server=ROOT / DEFAULT_SERVER, model=ROOT / DEFAULT_MODEL, port=18930,
            gpu_layers="0" if args.cpu else "99", log=state / "logs" / "memory-training.log"))
    try:
        examples += await training.embed_rows(rows, embedder, decisions=decisions)
    finally:
        if embedder is not None:
            await embedder.close()
    return training.isfinite_examples(examples)


async def main_async(args: argparse.Namespace) -> int:
    state: Path = args.state_root
    layers = LayerSet(state / "memory" / "layers")
    if args.list:
        for name in training.LAYERS:
            active = layers.get(name)
            print(f"{name:13} active: {active.version if active else 'fixed thresholds'}; "
                  f"saved: {', '.join(layers.versions(name)) or 'none'}")
        return 0
    if args.rollback:
        name, version = args.rollback
        layers.activate(name, version)
        print(f"{name} now uses {version}.")
        return 0
    if args.export_unlabelled:
        labelled = {str(r.get("decision_id")) for r in training.file_examples(
            sorted((state / "memory/labels").glob("*.jsonl")), "files")}
        count = training.export_unlabelled(state, args.database, args.export_unlabelled,
                                           labelled=labelled)
        print(f"Wrote {count} decisions to label: {args.export_unlabelled}. Fill in each "
              f"\"label\" and save the file into {state / 'memory/labels'}.")
        return 0

    examples = await gather(args, embed=args.train)
    th = Thresholds()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    reports: list[training.LayerReport] = []
    for name in args.layers or training.LAYERS:
        if not args.train:
            reports.append(training.count_layer(name, examples, min_examples=args.min,
                                                min_per_class=args.min_per_class))
            continue
        report, model = training.train_layer(name, examples, th=th, min_examples=args.min,
                                             min_per_class=args.min_per_class, stamp=stamp)
        if isinstance(model, LogisticLayer):
            training.adopt(report, model, layers, activate=args.adopt)
        reports.append(report)
    text = training.report_markdown(reports, trained=args.train)
    print(text)
    if args.train:
        folder = state / "memory" / "layers" / "reports"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{stamp}.md").write_text(text, encoding="utf-8")
        (folder / f"{stamp}.json").write_text(
            json.dumps([asdict(r) for r in reports], indent=2), encoding="utf-8")
        print(f"Report: {folder / (stamp + '.md')}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--state-root", type=Path, default=ROOT / ".local/manual-test")
    parser.add_argument("--database", type=Path, help="default: <state-root>/data/sora.db")
    parser.add_argument("--train", action="store_true", help="train (default: check only)")
    parser.add_argument("--adopt", action="store_true",
                        help="make a trained layer active when it beats the fixed policy")
    parser.add_argument("--layers", nargs="*", choices=training.LAYERS)
    parser.add_argument("--labels", nargs="*", default=[], help="more folders of label files")
    parser.add_argument("--include-fabricated", action="store_true",
                        help="also use training/memory/labels/fabricated (low weight)")
    parser.add_argument("--min", type=int, default=training.MIN_EXAMPLES)
    parser.add_argument("--min-per-class", type=int, default=training.MIN_PER_CLASS)
    parser.add_argument("--export-unlabelled", type=Path)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--rollback", nargs=2, metavar=("LAYER", "VERSION"))
    parser.add_argument("--cpu", action="store_true", help="embed on the CPU")
    args = parser.parse_args()
    args.database = args.database or args.state_root / "data" / "sora.db"
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
