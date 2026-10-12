"""Compile a fine-tuned Laya checkpoint to the GGUF SORA's laya runner loads.

    .local\\decision\\train-env\\Scripts\\python.exe scripts\\decision\\compile.py --run NAME

Uses ggmlc's own Laya compiler (examples/laya/compile_laya.py, fetched by setup-training.ps1),
pointed at the local checkpoint instead of a Hugging Face repository. The result is
.local/decision/runs/<run>/laya_sora_<quantize>.gguf. Point Settings -> Models -> Decision
layer -> Laya model GGUF at it, after checking it with scripts/decision/evaluate.py.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPILER = ROOT / ".local/decision/ggmlc-v0.9.7"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--run", required=True, help="name under .local/decision/runs/")
    parser.add_argument("--quantize", default="q8_0", choices=("f16", "q8_0", "ud_q4_k_m"))
    args = parser.parse_args()
    run = ROOT / ".local/decision/runs" / args.run
    checkpoint = run / "checkpoint"
    if not (checkpoint / "rl_agent_config.json").is_file():
        raise SystemExit(f"No checkpoint at {checkpoint}; run scripts/decision/train.py first.")
    os.environ.setdefault("USE_TF", "0")
    sys.path.insert(0, str(COMPILER))
    import compile_laya  # ggmlc's script; imports laya_trunk from the same folder

    compile_laya.CHECKPOINTS["sora"] = {
        "repo": str(checkpoint),  # laya.load reads a local directory as well as a repo
        "family": "english",
        "model_name": "laya-sora",
        "stem": "laya_sora",
        "pre_tokenizer": "gpt2",
    }
    output = run / f"laya_sora_{args.quantize}.gguf"
    compile_laya.compile_one("sora", args.quantize, output, max_batch=8, min_seq=64)
    print(f"next: uv run python scripts/decision/evaluate.py training/decision/seed_eval.jsonl "
          f"--model {output}")


if __name__ == "__main__":
    main()
