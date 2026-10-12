"""The decision layer: families, the laya daemon protocol, failing open, and narrowing tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from sora.contracts.companion_call import CompanionCall
from sora.decision.families import FAMILIES, allowed_operations, laya_questions
from sora.decision.gate import DecisionGate
from sora.decision.laya import LayaDecisionLayer
from sora.decision.settings import DecisionSettings, resolve_paths
from sora.runtime.read_tools import CompanionReadTools
from sora.runtime.read_turn import collect_reads

FAKE_DAEMON = """
import json, sys
print(json.dumps({"status": "ready", "model": "laya"}), flush=True)
for line in sys.stdin:
    request = json.loads(line)
    if "broken" in request["state"]:
        print("not json", flush=True)
        continue
    answers = {}
    for name in request["questions"]:
        p = 0.9 if name in request["state"] else 0.05
        answers[name] = {"type": "choice", "choice": "A" if p >= 0.5 else "B",
                         "probabilities": {"A": p, "B": 1 - p}}
    print(json.dumps({"id": request["id"], "answers": answers}), flush=True)
"""


def fake_layer(tmp_path: Path) -> LayaDecisionLayer:
    script = tmp_path / "fake_laya.py"
    script.write_text(FAKE_DAEMON, encoding="utf-8")
    return LayaDecisionLayer(tmp_path / "none.exe", tmp_path / "none.gguf",
                             command=(sys.executable, str(script)), timeout=10)


def test_families_unlock_their_operations_and_dependencies() -> None:
    assert allowed_operations([]) == {"finish", "remember", "remember_thought"}
    assert allowed_operations(["memory"]) == {"finish", "remember", "remember_thought",
                                              "find_memory", "present_memory"}
    # Pointing at a control needs the window list and an inspection first.
    assert {"look", "point", "list_windows", "inspect_window"} <= allowed_operations(["indicate"])
    assert allowed_operations(["unknown"]) == {"finish", "remember", "remember_thought"}
    questions = laya_questions()
    assert set(questions) == {family.name for family in FAMILIES}
    # Asked as a neutral two-option choice (Laya issue #156), not as noul.
    assert all(q["type"] == "choice" and set(q["criteria"]) == {"A", "B"}  # type: ignore[index]
               for q in questions.values())


def test_default_paths_follow_the_setup_script(tmp_path: Path) -> None:
    runner, model = resolve_paths(DecisionSettings(), tmp_path)
    assert runner == tmp_path / ".local/decision/laya-v0.9.7/laya.exe"
    assert model == tmp_path / ".local/decision/laya_english_q8_0.gguf"


@pytest.mark.asyncio
async def test_the_daemon_protocol_and_threshold(tmp_path: Path) -> None:
    layer = fake_layer(tmp_path)
    try:
        decision = await layer.decide("please check my memory and files", threshold=0.25)
        assert decision is not None
        assert decision.families == {"memory", "files"}
        assert decision.probabilities["motion"] == pytest.approx(0.05)
        assert layer.state == "ready"
    finally:
        await layer.close()


@pytest.mark.asyncio
async def test_a_broken_answer_fails_open_and_the_runner_restarts(tmp_path: Path) -> None:
    layer = fake_layer(tmp_path)
    try:
        assert await layer.decide("broken input", threshold=0.25) is None
        assert layer.state == "failed" and layer.process is None
        again = await layer.decide("memory", threshold=0.25)
        assert again is not None and again.families == {"memory"}
    finally:
        await layer.close()
    missing = LayaDecisionLayer(tmp_path / "none.exe", tmp_path / "none.gguf")
    assert await missing.decide("anything", threshold=0.25) is None
    assert missing.state == "unavailable"


@pytest.mark.parametrize("mode,expected", [
    ("off", None), ("shadow", None),
    ("enforce", {"finish", "remember", "remember_thought", "find_memory", "present_memory"}),
])
def test_only_enforce_narrows_the_tools(mode: str, expected: set[str] | None) -> None:
    from sora.decision.laya import Decision

    decision = Decision({"memory": 0.9}, frozenset({"memory"}), 20.0, "laya:test")
    settings = DecisionSettings(mode=mode)  # type: ignore[arg-type]
    assert DecisionGate.allowed(decision, settings) == expected
    assert DecisionGate.allowed(None, settings.model_copy(update={"mode": "enforce"})) is None


class OfferedOperations:
    def __init__(self) -> None:
        self.offered: list[frozenset[str]] = []

    async def choose_call(
        self, prompt: str, observations: str, operations: frozenset[str],
    ) -> CompanionCall:
        self.offered.append(operations)
        return CompanionCall.model_validate({"op": "finish"})


@pytest.mark.asyncio
async def test_the_brain_is_offered_only_the_chosen_families(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("sora.runtime.read_turn.desktop_directories", lambda: [])

    async def observe(request: Any) -> Any:
        raise AssertionError("no desktop reads in this test")

    provider = OfferedOperations()
    common: dict[str, Any] = {
        "provider": provider,
        "tools": CompanionReadTools(check=lambda _: None, observe=observe),
        "check_epoch": lambda: None, "file_read": True, "desktop_read": True,
        "timeout": 5, "budget": 4000, "avatar_control": True,
    }
    await collect_reads("sit down", **common)
    await collect_reads("sit down", allowed=allowed_operations(["motion"]), **common)
    everything, narrowed = provider.offered
    assert {"pose", "move", "read_file", "list_windows"} <= everything
    assert narrowed == {"finish", "pose", "move", "list_windows"}  # no self-memory here
    json.dumps(sorted(narrowed))  # trace-safe


def test_the_delegate_question_names_the_owners_agents() -> None:
    # Seen live 2026-10-08: "Ask Pip to check my packing list" was missed until Pip was named.
    questions = laya_questions(agent_names=("Cody", "Pip", "Pip", " "))
    delegate = questions["delegate"]["instructions"]  # type: ignore[index]
    assert "(Cody, Pip)" in delegate
    assert "Pip" not in questions["memory"]["instructions"]  # type: ignore[index]


@pytest.mark.asyncio
async def test_the_gate_stays_off_unless_an_owner_launch_enables_it(tmp_path: Path) -> None:
    gate = DecisionGate(tmp_path)
    assert await gate.decide("sit down", DecisionSettings(mode="enforce")) is None
    assert gate.layer is None  # no runner was even prepared
