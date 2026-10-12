"""Labelled decision data: one compact row per message, expanded to Laya's format when needed.

A row is ``{"message": str, "families": [str, ...], "source": str}``: the tool families that
message needs (empty for plain conversation). Sources say how trustworthy a label is:

* ``owner``     -- written or corrected by the owner (the best labels);
* ``trace``     -- derived from what the brain used in shadow mode (noisy: the brain can skip
                   a tool it needed, or use one it did not);
* ``seed``      -- hand-written starter examples, not the owner's own phrasing.

Families come from a catalogue: SORA's own (sora.decision.families) plus extension-style
families in training/decision/extension_families.json. Laya is trained on the *general* question
"does this message need <description>?", with each row asking about its own families and a random
sample of others, so a family added later by an extension or plugin works from its description
alone. Some families are held out of training entirely to measure exactly that.

No torch here: Core, the evaluation script and the training script all read the same rows.
See docs/runbooks/TRAINING_LAYA.md.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from sora.decision.families import FAMILIES, Family, laya_questions

EXTENSIONS = Path(__file__).resolve().parents[3] / "training/decision/extension_families.json"

# Operation -> the family that most directly asked for it, for labelling from traces.
# list_windows also serves motion, indicate and view_window; on its own it means "windows".
OPERATION_FAMILY = {
    "list_windows": "windows", "inspect_window": "windows",
    "list_files": "files", "search_files": "files", "read_file": "files",
    "find_memory": "memory", "present_memory": "memory",  # remember(_thought): no family
    "pose": "motion", "move": "motion",
    "look": "indicate", "point": "indicate",
    "list_agents": "delegate", "delegate": "delegate",
    "view_window": "view_window",
}
SOURCES = ("owner", "trace", "seed")


@dataclass(frozen=True)
class Example:
    message: str
    families: frozenset[str]
    source: str

    def to_json(self) -> str:
        return json.dumps({"message": self.message, "families": sorted(self.families),
                           "source": self.source}, ensure_ascii=False)


@dataclass(frozen=True)
class Catalogue:
    families: dict[str, Family]
    held_out: frozenset[str]  # never used for training; evaluation only

    def trainable(self) -> list[Family]:
        return [f for name, f in self.families.items() if name not in self.held_out]


def load_catalogue(extensions: Path = EXTENSIONS) -> Catalogue:
    families = {family.name: family for family in FAMILIES}
    held_out: frozenset[str] = frozenset()
    if extensions.is_file():
        data = json.loads(extensions.read_text(encoding="utf-8"))
        for name, description in data["families"].items():
            families[name] = Family(name, description, frozenset())
        held_out = frozenset(data.get("held_out", ()))
    return Catalogue(families, held_out)


def read_examples(path: Path, catalogue: Catalogue | None = None) -> list[Example]:
    known = (catalogue or load_catalogue()).families
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        data = json.loads(line)
        families = frozenset(data["families"])
        unknown = families - known.keys()
        if unknown or data.get("source", "seed") not in SOURCES or not data["message"].strip():
            raise ValueError(f"{path}:{number}: invalid row ({sorted(unknown) or data})")
        rows.append(Example(data["message"], families, data.get("source", "seed")))
    return rows


def families_from_operations(chosen: Iterable[str]) -> frozenset[str]:
    """Label a traced turn by what the brain used.

    A window list made only to walk to, point at or look closer at a window belongs to that
    action; "windows" is kept when a window was actually read (inspect_window) for its own sake.
    """
    used = {op for op in chosen if op != "finish"}
    families = {OPERATION_FAMILY[op] for op in used if op in OPERATION_FAMILY}
    if families - {"windows"}:
        read_for_itself = "inspect_window" in used and "indicate" not in families
        if not read_for_itself:
            families.discard("windows")
    return frozenset(families)


def laya_rows(
    examples: Iterable[Example],
    catalogue: Catalogue,
    *,
    negatives: int = 5,
    seed: int = 0,
    agent_names: Iterable[str] = (),
) -> Iterator[dict[str, object]]:
    """Expand to laya.train's JSONL for *general* tool-family training.

    Each row asks about the message's own families plus ``negatives`` others drawn at random from
    the trainable catalogue, in random order, with the A/B (yes/no) options randomly swapped, so
    the model learns to read descriptions rather than memorise names or positions. Held-out
    families never appear.
    """
    rng = random.Random(seed)
    trainable = catalogue.trainable()
    names = tuple(agent_names)
    for example in examples:
        if example.families & catalogue.held_out:
            continue
        own = [catalogue.families[name] for name in sorted(example.families)]
        others = [f for f in trainable if f.name not in example.families]
        asked = own + rng.sample(others, min(negatives, len(others)))
        rng.shuffle(asked)
        questions = laya_questions(asked, agent_names=names)
        expected = {}
        for family in asked:
            question = questions[family.name]
            assert isinstance(question, dict)
            yes = family.name in example.families
            if rng.random() < 0.5:  # swap which letter means yes
                question["criteria"] = {"A": "no, it does not", "B": "yes, it needs that"}
                expected[family.name] = "B" if yes else "A"
            else:
                expected[family.name] = "A" if yes else "B"
        yield {"state": example.message, "questions": questions, "expected": expected}
