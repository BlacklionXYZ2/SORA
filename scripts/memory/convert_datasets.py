"""Turn the public datasets in training/memory/datasets/ into label files for the memory layers.

    uv run --with pyarrow python scripts/memory/convert_datasets.py --out <folder>

``pyarrow`` is needed only here (PAWS is Parquet); it is not one of SORA's dependencies.

Writes ``bootstrap_*.jsonl`` training labels and ``test_longmemeval_*.jsonl`` test labels into
``--out`` (normally a profile's ``memory/labels`` folder, which ``train_layers.py`` reads; keep the
test files elsewhere, see ``--test-out``). Every training row is a bootstrap example: weight
``--weight`` (default 0.5, half an owner label) and a ``group`` so related rows stay on one side
of the held-out split. What each dataset is used for: training/memory/datasets/README.md.

- **Dialogue NLI** (comparison), its verified set: pairs all three annotators agreed on (the
  training split's automatic labels proved noisy). Each sentence comes with a fact triple
  (subject, relation, value). Same subject and relation with the same value: "same" (a
  repeat). Same subject and relation with a different value, labelled a contradiction:
  "updated". A neutral pair about a different subject or relation: "unrelated".
- **PAWS** (comparison), paraphrases only: the same fact in different words ("same"). Its
  non-paraphrases are left out: they are usually about the same subject with a detail changed,
  which is neither "different subject" nor a clean "update" in the memory manager's terms.
- **Multi-Session Chat** persona summaries (acceptance). A line that revealed something about
  the speaker (it has a ``persona_text``) was worth keeping (1); one that didn't was not (0).
  Facts the speaker revealed earlier in the conversation are the "existing" memories.
- **Synthetic-Persona-Chat** (relevance). The real reply to a line belongs with it (1); a reply
  from another conversation does not (0).
- **Written update pairs** (comparison): ``training/memory/labels/written/update_pairs.jsonl``,
  80 owner-style "same" and "updated" pairs written by Opus 5.5, with change words, numbers and
  negations on both sides so the update layer can't learn "now means updated".
- **LongMemEval** (test only, never training). Knowledge-update questions with exactly two dated
  evidence turns give real (older, newer) update pairs; each newer turn paired with a turn from a
  different question gives an unrelated pair. Evidence turns are worth keeping; user turns from
  sessions holding no evidence are not.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import random
import re
import tarfile
import zipfile
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATASETS = ROOT / "training" / "memory" / "datasets"
MAX_CHARS = 1500  # long chat turns are cut here before embedding


def dnli_rows(path: Path, per_kind: int, rng: random.Random, weight: float) -> list[dict[str, Any]]:
    with zipfile.ZipFile(path) as archive:
        pairs = json.loads(archive.read("dnli/dialogue_nli/dialogue_nli_verified_test.jsonl"))
    pairs = [p for p in pairs if p["annotation1"] == p["annotation2"] == p["annotation3"]
             == p["label"]]
    kinds: dict[str, list[dict[str, Any]]] = {"same": [], "updated": [], "unrelated": []}
    for pair in pairs:
        (s1, r1, o1), (s2, r2, o2) = pair["triple1"], pair["triple2"]
        same_fact = s1 == s2 and r1 == r2
        if pair["label"] == "positive" and same_fact and o1 == o2:
            kinds["same"].append(pair)
        elif pair["label"] == "negative" and same_fact and o1 != o2:
            kinds["updated"].append(pair)
        elif pair["label"] == "neutral" and not same_fact:
            kinds["unrelated"].append(pair)
    rows = []
    for kind, found in kinds.items():
        for pair in rng.sample(found, min(per_kind, len(found))):
            s, r, _ = pair["triple1"]
            rows.append({"layer": "comparison", "a": pair["sentence1"], "b": pair["sentence2"],
                         "label": kind, "days": rng.randint(1, 180), "weight": weight,
                         "group": f"dnli:{s}|{r}", "source": "dialogue_nli"})
    return rows


def paws_rows(path: Path, count: int, rng: random.Random, weight: float) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq  # only this converter needs it

    paraphrases = [r for r in pq.read_table(path).to_pylist() if int(r["label"]) == 1]
    return [{"layer": "comparison", "a": pair["sentence1"], "b": pair["sentence2"],
             "label": "same", "days": rng.randint(1, 180), "weight": weight,
             "group": f"paws:{pair['id']}", "source": "paws"}
            for pair in rng.sample(paraphrases, min(count, len(paraphrases)))]


def msc_rows(path: Path, per_class: int, rng: random.Random, weight: float) -> list[dict[str, Any]]:
    keep: list[dict[str, Any]] = []
    drop: list[dict[str, Any]] = []
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            if not re.fullmatch(r"msc/msc_personasummary/session_\d/train\.txt", member.name):
                continue
            stream = archive.extractfile(member)
            if stream is None:
                continue
            for number, line in enumerate(io.TextIOWrapper(stream, encoding="utf-8")):
                dialog = json.loads(line)["dialog"]
                known: dict[str, list[str]] = {}
                for turn in dialog:
                    speaker = str(turn["id"])
                    row = {"layer": "acceptance", "text": turn["text"],
                           "existing": known.get(speaker, [])[-2:], "weight": weight,
                           "group": f"msc:{member.name}:{number}", "source": "msc"}
                    if turn.get("persona_text"):
                        keep.append(dict(row, label=1))
                        known.setdefault(speaker, []).append(str(turn["persona_text"]))
                    else:
                        drop.append(dict(row, label=0))
    return (rng.sample(keep, min(per_class, len(keep)))
            + rng.sample(drop, min(per_class, len(drop))))


def _spc_lines(conversation: str) -> list[str]:
    lines = []
    for line in conversation.splitlines():
        _, _, text = line.partition(":")
        if text.strip():
            lines.append(text.strip())
    return lines


def spc_rows(path: Path, per_class: int, rng: random.Random, weight: float) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8", newline="") as file:
        conversations = [_spc_lines(r["Best Generated Conversation"]) for r in csv.DictReader(file)]
    conversations = [c for c in conversations if len(c) >= 4]
    rows = []
    for _ in range(per_class):
        index = rng.randrange(len(conversations))
        lines = conversations[index]
        turn = rng.randrange(len(lines) - 1)
        other = rng.choice([c for i, c in enumerate(conversations[:500]) if i != index])
        group = f"spc:{index}"
        rows.append({"layer": "relevance", "owner": lines[turn], "part": lines[turn + 1],
                     "part_type": "reply", "label": 1, "weight": weight, "group": group,
                     "source": "synthetic_persona_chat"})
        rows.append({"layer": "relevance", "owner": lines[turn], "part": rng.choice(other),
                     "part_type": "reply", "label": 0, "weight": weight, "group": group,
                     "source": "synthetic_persona_chat"})
    return rows


def _date(value: str) -> datetime:
    return datetime.strptime(value.split(" (")[0] + value.split(")")[-1], "%Y/%m/%d %H:%M")


def longmemeval_rows(oracle: Path, short: Path, per_class: int,
                     rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Test rows: (comparison pairs, acceptance turns). Never used for training."""
    questions = json.loads(oracle.read_text("utf-8"))
    user_turns = [(q["question_id"], t["content"]) for q in questions
                  for s in q["haystack_sessions"] for t in s if t["role"] == "user"]
    pairs = []
    for question in questions:
        if question["question_type"] != "knowledge-update":
            continue
        evidence = [(_date(date), turn["content"]) for date, session in
                    zip(question["haystack_dates"], question["haystack_sessions"], strict=True)
                    for turn in session if turn.get("has_answer") and turn["role"] == "user"]
        if len(evidence) != 2:
            continue
        (old_date, old), (new_date, new) = sorted(evidence, key=lambda e: e[0])
        days = max(0.0, (new_date - old_date).total_seconds() / 86400)
        group = f"lme:{question['question_id']}"
        pairs.append({"layer": "comparison", "a": old[:MAX_CHARS], "b": new[:MAX_CHARS],
                      "label": "updated", "days": days, "group": group, "source": "longmemeval"})
        other = rng.choice([t for qid, t in user_turns if qid != question["question_id"]])
        pairs.append({"layer": "comparison", "a": other[:MAX_CHARS], "b": new[:MAX_CHARS],
                      "label": "unrelated", "days": days, "group": group,
                      "source": "longmemeval"})
    keep = [t["content"] for q in questions for s in q["haystack_sessions"] for t in s
            if t.get("has_answer") and t["role"] == "user"]
    filler = []
    for question in json.loads(short.read_text("utf-8")):
        evidence_sessions = set(question["answer_session_ids"])
        for session_id, session in zip(question["haystack_session_ids"],
                                       question["haystack_sessions"], strict=True):
            if session_id not in evidence_sessions:
                filler += [t["content"] for t in session if t["role"] == "user"]
    turns = ([{"layer": "acceptance", "text": t[:MAX_CHARS], "label": 1, "source": "longmemeval"}
              for t in rng.sample(keep, min(per_class, len(keep)))]
             + [{"layer": "acceptance", "text": t[:MAX_CHARS], "label": 0,
                 "source": "longmemeval"} for t in rng.sample(filler, min(per_class, len(filler)))])
    return pairs, turns


def written_rows(path: Path, weight: float) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    return [dict(row, weight=weight, group=f"written:{i}", source="written")
            for i, row in enumerate(rows)]


def write(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def _summary(rows: list[dict[str, Any]]) -> Iterator[str]:
    labels: dict[str, int] = {}
    for row in rows:
        labels[str(row["label"])] = labels.get(str(row["label"]), 0) + 1
    yield ", ".join(f"{label}: {count}" for label, count in sorted(labels.items()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="folder for training labels")
    parser.add_argument("--test-out", type=Path,
                        help="folder for test labels (default: --out/../tests)")
    parser.add_argument("--datasets", type=Path, default=DATASETS)
    parser.add_argument("--weight", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=20261023)
    parser.add_argument("--comparison-per-kind", type=int, default=700)
    parser.add_argument("--paws", type=int, default=300, help="PAWS paraphrase pairs")
    parser.add_argument("--acceptance-per-class", type=int, default=750)
    parser.add_argument("--relevance-per-class", type=int, default=750)
    parser.add_argument("--test-per-class", type=int, default=300)
    args = parser.parse_args()
    rng = random.Random(args.seed)
    folder: Path = args.datasets
    test_out: Path = args.test_out or args.out.parent / "tests"
    outputs = {
        args.out / "bootstrap_dialogue_nli.jsonl": dnli_rows(
            folder / "dnli.zip", args.comparison_per_kind, rng, args.weight),
        args.out / "bootstrap_written_updates.jsonl": written_rows(
            ROOT / "training" / "memory" / "labels" / "written" / "update_pairs.jsonl",
            args.weight),
        args.out / "bootstrap_paws.jsonl": paws_rows(
            folder / "paws_train.parquet", args.paws, rng, args.weight),
        args.out / "bootstrap_msc.jsonl": msc_rows(
            folder / "msc_v0.1.tar.gz", args.acceptance_per_class, rng, args.weight),
        args.out / "bootstrap_synthetic_persona_chat.jsonl": spc_rows(
            folder / "spc_Synthetic-Persona-Chat_train.csv", args.relevance_per_class, rng,
            args.weight),
    }
    pairs, turns = longmemeval_rows(folder / "longmemeval_oracle.json",
                                    folder / "longmemeval_s_cleaned.json",
                                    args.test_per_class, rng)
    outputs[test_out / "test_longmemeval_comparison.jsonl"] = pairs
    outputs[test_out / "test_longmemeval_acceptance.jsonl"] = turns
    for path, rows in outputs.items():
        count = write(path, rows)
        print(f"{path}: {count} rows ({next(_summary(rows))})")


if __name__ == "__main__":
    main()
