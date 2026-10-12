"""Fine-tune Laya for SORA's decision layer: general "does this message need <tool family>?".

Run with the training environment (scripts/decision/setup-training.ps1), not SORA's own:

    .local\\decision\\train-env\\Scripts\\python.exe scripts\\decision\\train.py ^
        training\\decision\\seed_train.jsonl .local\\decision\\data\\owner.jsonl --name my-first-run

Then build the GGUF SORA runs with scripts/decision/compile.py and compare it with
scripts/decision/evaluate.py. Everything for a run lands in .local/decision/runs/<name>/:
the expanded laya rows, the fine-tuned checkpoint, and summary.json.
See docs/runbooks/TRAINING_LAYA.md for what each option means.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("USE_TF", "0")  # transformers' TensorFlow probe can hang model building

from sora.decision.dataset import laya_rows, load_catalogue, read_examples  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("data", nargs="+", type=Path,
                        help="labelled JSONL files (message, families, source)")
    parser.add_argument("--name", default=datetime.now().strftime("run-%Y%m%d-%H%M%S"))
    parser.add_argument("--base", type=Path, default=ROOT / ".local/models/laya",
                        help="checkpoint to start from (a laya.load directory)")
    parser.add_argument("--eval", type=Path, default=ROOT / "training/decision/seed_eval.jsonl",
                        help="held-out messages laya reports on during training")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--negatives", type=int, default=5,
                        help="other families asked about per message (general training)")
    parser.add_argument("--repeats", type=int, default=3,
                        help="copies of each message with different families sampled")
    parser.add_argument("--micro-batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--encoder-lr", type=float, default=2e-5)
    parser.add_argument("--head-lr", type=float, default=1e-4)
    parser.add_argument("--freeze-encoder", action="store_true",
                        help="train only the decision head (fast, little memory; a smoke test)")
    parser.add_argument("--limit", type=int, default=0, help="use only the first N messages")
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    from laya.train import TrainConfig, finetune  # the training environment only

    catalogue = load_catalogue()
    examples = [e for path in args.data for e in read_examples(path, catalogue)]
    if args.limit:
        examples = examples[: args.limit]
    run = ROOT / ".local/decision/runs" / args.name
    run.mkdir(parents=True, exist_ok=False)
    train_path, eval_path = run / "train.laya.jsonl", run / "eval.laya.jsonl"
    with train_path.open("w", encoding="utf-8") as out:
        for repeat in range(args.repeats):
            for row in laya_rows(examples, catalogue, negatives=args.negatives, seed=repeat):
                out.write(json.dumps(row) + "\n")
    eval_examples = read_examples(args.eval, catalogue)
    with eval_path.open("w", encoding="utf-8") as out:
        for row in laya_rows(eval_examples, catalogue, negatives=args.negatives, seed=999):
            out.write(json.dumps(row) + "\n")

    config = TrainConfig(
        epochs=args.epochs, micro_batch=args.micro_batch, grad_accum=args.grad_accum,
        encoder_lr=args.encoder_lr, head_lr=args.head_lr, loss="soft-ce",
        shuffle_options=("choice",), freeze_encoder=args.freeze_encoder,
        eval_data=str(eval_path),
    )
    print(f"{len(examples)} messages x {args.repeats} -> {train_path}")
    summary = finetune(str(train_path), str(args.base), str(run / "checkpoint"), config,
                       device=args.device)
    record = {
        "name": args.name, "base": str(args.base), "data": [str(p) for p in args.data],
        "messages": len(examples), "held_out_families": sorted(catalogue.held_out),
        "config": vars(args) | {"data": None, "base": None, "eval": str(args.eval)},
        "laya_summary": summary, "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    (run / "summary.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    print(f"checkpoint: {run / 'checkpoint'}\nnext: scripts/decision/compile.py --run {args.name}")


if __name__ == "__main__":
    main()
