"""Turn SORA's decision traces into labelled training rows.

    uv run python scripts/decision/export_traces.py
    uv run python scripts/decision/export_traces.py --state .local/manual-test --since 2026-10-09

Each companion turn leaves two traces with the same correlation ID:
  decision.families    -- the message, and what Laya scored (mode, probabilities);
  companion.read_turn  -- the operations the brain was offered and actually chose.
Only shadow-mode turns are used: in enforce mode the brain could not choose a tool Laya hid, so
its choices would just repeat Laya's decisions back to it.

Labels come from what the brain *used* (sora.decision.dataset.families_from_operations), so they
are noisy. Review the file before training: fix a row's "families", set "source": "owner" on
rows you have checked, and delete rows you would not want learned. Output goes to
.local/decision/data/ (git-ignored: it contains your messages).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sora.decision.dataset import Example, families_from_operations  # noqa: E402


def export(database: Path, since: str | None) -> list[tuple[Example, dict[str, object]]]:
    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        query = ("SELECT correlation_id, phase, timestamp, fields_json FROM traces "
                 "WHERE phase IN ('decision.families', 'companion.read_turn')")
        parameters: tuple[str, ...] = ()
        if since:
            query += " AND timestamp >= ?"
            parameters = (since,)
        turns: dict[str, dict[str, dict[str, object]]] = {}
        for correlation, phase, _, fields in connection.execute(query, parameters):
            turns.setdefault(correlation, {})[phase] = json.loads(fields)
    finally:
        connection.close()
    rows = []
    for turn in turns.values():
        decision, read = turn.get("decision.families"), turn.get("companion.read_turn")
        if not decision or not read or decision.get("mode") != "shadow":
            continue
        message = str(decision.get("message") or "").strip()
        if not message:
            continue  # traces from before messages were recorded
        raw = read.get("chosen")
        chosen = [str(op) for op in raw] if isinstance(raw, list) else []
        example = Example(message, families_from_operations(chosen), "trace")
        rows.append((example, {"laya": decision.get("probabilities"), "chosen": chosen}))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--state", type=Path, default=ROOT / ".local/manual-test",
                        help="SORA state folder (contains data/sora.db)")
    parser.add_argument("--since", default=None, help="only traces on or after this ISO date")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rows = export(args.state / "data/sora.db", args.since)
    output = args.output or (ROOT / ".local/decision/data"
                             / f"traces-{datetime.now():%Y%m%d-%H%M%S}.jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as out:
        out.write("# Review before training: fix families, mark checked rows \"source\": \"owner\"."
                  " _context is ignored.\n")
        for example, context in rows:
            row = json.loads(example.to_json())
            row["_context"] = context  # what Laya scored and the brain chose, for review
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
    def offered(context: dict[str, object]) -> set[str]:
        scores = context["laya"]
        return {k for k, v in scores.items() if v >= 0.25} if isinstance(scores, dict) else set()

    disagree = sum(1 for example, context in rows if not example.families <= offered(context))
    print(f"{len(rows)} shadow-mode turns -> {output}")
    print(f"{disagree} where Laya (at 0.25) would have hidden a tool the brain used")


if __name__ == "__main__":
    main()
