"""Reload motion model: the supervisor's handover, with a fake motion service (2026-10-27)."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from sora.embodiment import motion_service
from sora.embodiment.motion_service import MotionSupervisor
from sora.embodiment.motion_settings import MotionSettings
from sora.runtime.app_settings import (
    AppSettings,
    AppSettingsController,
    ReloadRequest,
    SettingsEdit,
)

FRAME = {"root": [0.0, 0.9, 0.0], "rot": [[0.0, 0.0, 0.0, 1.0]] * 22,
         "contacts": [True, True, True, True]}
# Speaks service.py's protocol: ready, then (after a seed or start) one chunk every 50 ms whose
# prompt is the last signal's key. Every message it receives is appended to a log file.
FAKE = """
import json, sys, threading, time
log = open(sys.argv[1], "a")
mode = sys.argv[2]
if mode == "fail":
    print(json.dumps({"type": "error", "message": "load failed: no GPU"}), flush=True)
    sys.exit(0)
print(json.dumps({"type": "ready", "model": "fake"}), flush=True)
state = {"go": False, "key": "-|-|-"}
def read():
    for line in sys.stdin:
        message = json.loads(line)
        log.write(line); log.flush()
        if message["type"] in ("seed", "start"): state["go"] = True
        if message["type"] == "signal": state["key"] = message["key"]
        if message["type"] == "stop": break
    state["stop"] = True
threading.Thread(target=read, daemon=True).start()
seq = 0
while not state.get("stop"):
    if state["go"]:
        frame = {"root": [0, 0.9, 0], "rot": [[0, 0, 0, 1]] * 22, "contacts": [True] * 4}
        print(json.dumps({"type": "chunk", "seq": seq, "t0": seq * 0.4, "fps": 60,
                          "prompt": state["key"], "frames": [frame] * 24}), flush=True)
        seq += 1
    time.sleep(0.05)
print(json.dumps({"type": "stopped"}), flush=True)
"""


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, list[str]]:
    script = tmp_path / "fake_service.py"
    script.write_text(FAKE, encoding="utf-8")
    log = tmp_path / "received.jsonl"
    mode = ["ok"]
    monkeypatch.setattr(motion_service, "service_command",
                        lambda settings, project: [sys.executable, str(script), str(log), mode[0]])
    monkeypatch.setattr(motion_service, "SEED_WAIT_SECONDS", 0.5)
    return log, mode


async def drain(queue: asyncio.Queue[dict[str, Any]], until: str, timeout: float = 15.0
                ) -> list[dict[str, Any]]:
    """Messages to the player until one with ``op == until`` (inclusive)."""
    seen: list[dict[str, Any]] = []
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        message = await asyncio.wait_for(queue.get(), remaining)
        seen.append(message)
        if message["op"] == until:
            return seen


def received(log: Path) -> list[dict[str, Any]]:
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text("utf-8").splitlines()]


@pytest.mark.asyncio
async def test_reload_records_seeds_the_model_and_hands_her_over(
    tmp_path: Path, fake: tuple[Path, list[str]],
) -> None:
    log, _ = fake
    supervisor = MotionSupervisor(tmp_path)
    player = supervisor.register()
    assert (await player.get()) == {"op": "source", "source": "algorithmic"}
    await supervisor.from_player({"type": "embodiment.motion", "op": "signal",
                                  "key": "walk|-|-", "velocity": [0.0, 1.2]})
    status = await supervisor.reload(MotionSettings(engine="ardy"))
    assert status["state"] == "starting"
    # She stays on her own poses and starts recording at once.
    first = await drain(player, "record")
    assert first[-1]["seconds"] == motion_service.RECORD_SECONDS
    await drain(player, "seed_request")
    await supervisor.from_player({"type": "embodiment.motion", "op": "seed",
                                  "seed": {"fps": 60, "frames": [FRAME, FRAME, FRAME]}})
    handover = await drain(player, "source")
    assert handover[-1]["source"] == "ardy"
    assert any(m["op"] == "chunk" for m in handover)  # the first chunk precedes the switch
    assert supervisor.status()["state"] == "running"
    chunk = next(m for m in handover if m["op"] == "chunk")["chunk"]
    assert chunk["prompt"] == "walk|-|-" and len(chunk["frames"]) == 24
    await supervisor.close()
    messages = received(log)
    assert [m["type"] for m in messages][:2] == ["seed", "signal"]
    assert len(messages[0]["frames"]) == 3
    assert messages[-1]["type"] == "stop"


@pytest.mark.asyncio
async def test_without_a_recording_the_model_starts_standing(
    tmp_path: Path, fake: tuple[Path, list[str]],
) -> None:
    log, _ = fake
    supervisor = MotionSupervisor(tmp_path)
    player = supervisor.register()
    await supervisor.reload(MotionSettings(engine="ardy"))
    await drain(player, "seed_request")  # nobody answers
    assert (await drain(player, "source"))[-1]["source"] == "ardy"
    await supervisor.close()
    assert [m["type"] for m in received(log)][:2] == ["start", "signal"]
    assert received(log)[1]["key"] == "-|-|-" and received(log)[1]["velocity"] == [0.0, 0.0]


@pytest.mark.asyncio
async def test_a_model_that_fails_to_load_leaves_her_on_her_own_poses(
    tmp_path: Path, fake: tuple[Path, list[str]],
) -> None:
    _, mode = fake
    mode[0] = "fail"
    supervisor = MotionSupervisor(tmp_path)
    player = supervisor.register()
    await supervisor.reload(MotionSettings(engine="ardy"))
    for _ in range(100):
        if supervisor.status()["state"] == "failed":
            break
        await asyncio.sleep(0.05)
    status = supervisor.status()
    assert status["state"] == "failed" and "no GPU" in status["error"]
    sources = [m.get("source") for m in await drain(player, "record") if m["op"] == "source"]
    assert "ardy" not in sources
    await supervisor.close()


@pytest.mark.asyncio
async def test_switching_back_stops_the_model_and_custom_models_are_refused(
    tmp_path: Path, fake: tuple[Path, list[str]],
) -> None:
    log, _ = fake
    supervisor = MotionSupervisor(tmp_path)
    player = supervisor.register()
    await supervisor.reload(MotionSettings(engine="ardy"))
    await drain(player, "seed_request")
    await drain(player, "source")
    process = supervisor.process
    status = await supervisor.reload(MotionSettings(engine="algorithmic"))
    assert status["state"] == "algorithmic" and supervisor.process is None
    assert process is not None and process.returncode is not None  # stopped, not orphaned
    assert (await drain(player, "source"))[-1]["source"] == "algorithmic"
    assert received(log)[-1]["type"] == "stop"
    custom = await supervisor.reload(MotionSettings(engine="custom"))
    assert custom["state"] == "failed" and "only ARDY" in custom["error"]
    await supervisor.close()


@pytest.mark.asyncio
async def test_a_missing_ardy_install_fails_with_the_missing_file(tmp_path: Path) -> None:
    supervisor = MotionSupervisor(tmp_path / "SORA")
    status = await supervisor.reload(MotionSettings(engine="ardy"))
    assert status["state"] == "failed" and "isn't installed" in status["error"]
    assert "python.exe" in status["error"]


@pytest.mark.asyncio
async def test_bad_player_messages_are_rejected(tmp_path: Path) -> None:
    supervisor = MotionSupervisor(tmp_path)
    for bad in ({"op": "signal", "key": "walk|-|-"},  # no velocity
                {"op": "signal", "key": "rm -rf", "velocity": [0, 0]},
                {"op": "seed", "seed": {"fps": 60, "frames": [FRAME]}},  # one frame
                {"op": "teleport"}):
        with pytest.raises(ValueError):
            await supervisor.from_player({"type": "embodiment.motion", **bad})


def test_motion_settings_apply_with_reload_motion_model_not_a_restart(tmp_path: Path) -> None:
    controller = AppSettingsController(tmp_path, AppSettings())
    tiers = {f["key"]: f["tier"] for f in controller.projection()["fields"]}
    assert {tiers[f"motion.{name}"] for name in MotionSettings.model_fields} == {"motion_reload"}
    controller.save(SettingsEdit(version=10, expected_revision=controller.saved.revision,
                                 changes={"motion.engine": "ardy"}))
    projection = controller.projection()
    assert projection["motion_reload_required"] and not projection["restart_required"]
    assert not projection["model_reload_required"]  # the brain's Reload model is unaffected
    projection = controller.apply_motion(ReloadRequest(expected_revision=controller.saved.revision))
    assert controller.active.motion.engine == "ardy"
    assert not projection["motion_reload_required"]
    with pytest.raises(ValueError):
        controller.apply_motion(ReloadRequest(expected_revision=0))  # stale revision
