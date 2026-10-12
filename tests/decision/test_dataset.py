"""Training data for the decision layer: catalogue, general-training rows, trace labels, export."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from sora.decision.dataset import (
    Example,
    families_from_operations,
    laya_rows,
    load_catalogue,
    read_examples,
)

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "training/decision"


def test_seed_sets_are_valid_and_disjoint() -> None:
    catalogue = load_catalogue()
    train = read_examples(DATA / "seed_train.jsonl", catalogue)
    evaluate = read_examples(DATA / "seed_eval.jsonl", catalogue)
    unseen = read_examples(DATA / "seed_eval_unseen.jsonl", catalogue)
    assert {e.message for e in train}.isdisjoint({e.message for e in evaluate + unseen})
    # Held-out families are never in training data, only in the unseen evaluation.
    assert not any(e.families & catalogue.held_out for e in train)
    assert {"calendar", "smart_home"} <= {f for e in unseen for f in e.families}
    assert catalogue.held_out == {"calendar", "smart_home"}


def test_rows_ask_about_own_families_plus_sampled_others_with_swapped_letters() -> None:
    catalogue = load_catalogue()
    example = Example("Pause the music and wave", frozenset({"media", "motion"}), "seed")
    rows = list(laya_rows([example] * 40, catalogue, negatives=4, seed=1))
    swapped = 0
    for row in rows:
        questions, expected = row["questions"], row["expected"]
        assert isinstance(questions, dict) and isinstance(expected, dict)
        assert {"media", "motion"} <= questions.keys()
        assert len(questions) == 6 and not questions.keys() & catalogue.held_out
        for name, question in questions.items():
            letter = expected[name]
            meaning = question["criteria"][letter]
            assert meaning.startswith("yes") == (name in example.families)
            swapped += question["criteria"]["A"].startswith("no")
    asked = 0
    for row in rows:
        assert isinstance(row["questions"], dict)
        asked += len(row["questions"])
    assert 0 < swapped < asked
    held = Example("Turn off the lights", frozenset({"smart_home"}), "seed")
    assert list(laya_rows([held], catalogue)) == []


@pytest.mark.parametrize("chosen,expected", [
    (["finish"], set()),
    (["find_memory", "finish"], {"memory"}),
    (["list_windows", "move"], {"motion"}),
    (["list_windows", "inspect_window", "point"], {"indicate"}),
    (["list_windows", "inspect_window"], {"windows"}),
    (["list_windows", "view_window"], {"view_window"}),
    (["inspect_window", "delegate"], {"windows", "delegate"}),
])
def test_trace_labels_follow_what_the_brain_used(chosen: list[str], expected: set[str]) -> None:
    assert families_from_operations(chosen) == expected


def test_export_pairs_shadow_decisions_with_what_the_brain_chose(tmp_path: Path) -> None:
    database = tmp_path / "data/sora.db"
    database.parent.mkdir()
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE traces (trace_id TEXT, correlation_id TEXT, message_id TEXT, "
                       "task_id TEXT, run_id TEXT, phase TEXT, timestamp TEXT, duration_ms REAL, "
                       "fields_json TEXT)")

    def trace(correlation: str, phase: str, fields: dict[str, object]) -> None:
        connection.execute("INSERT INTO traces VALUES (?, ?, NULL, NULL, NULL, ?, ?, NULL, ?)",
                           (correlation + phase, correlation, phase, "2026-10-09T10:00:00",
                            json.dumps(fields)))

    trace("t1", "decision.families", {"mode": "shadow", "message": "What's my favourite colour?",
                                      "probabilities": {"memory": 0.1}})
    trace("t1", "companion.read_turn", {"chosen": ["find_memory", "finish"]})
    trace("t2", "decision.families", {"mode": "enforce", "message": "Wave", "probabilities": {}})
    trace("t2", "companion.read_turn", {"chosen": ["pose"]})
    trace("t3", "decision.families", {"mode": "shadow", "message": "Hi", "probabilities": {}})
    connection.commit()
    connection.close()

    spec = importlib.util.spec_from_file_location("export_traces",
                                                  ROOT / "scripts/decision/export_traces.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = module.export(database, None)
    # Only t1: t2 was enforced (labels would echo Laya), t3 has no brain outcome.
    assert [(e.message, set(e.families), e.source) for e, _ in rows] == [
        ("What's my favourite colour?", {"memory"}, "trace"),
    ]
    output = tmp_path / "out.jsonl"
    output.write_text("\n".join(json.loads(e.to_json()) and e.to_json() for e, _ in rows),
                      encoding="utf-8")
    assert read_examples(output)[0].families == {"memory"}
