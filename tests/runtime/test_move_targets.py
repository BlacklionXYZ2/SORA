"""SORA's move call: semantic destinations Core resolves, pace, and a pose on arrival."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from sora.contracts.companion_call import Move, call_schema
from sora.contracts.desktop import DesktopNode
from sora.contracts.embodiment import EmbodimentVerb, MonitorDescriptor, ScreenRect
from sora.embodiment.local_player import RUN_SPEED_PX_PER_SEC, WALK_SPEED_PX_PER_SEC
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import SettingsEdit
from sora.runtime.read_tools import CompanionReadTools
from sora.runtime.read_turn import collect_reads
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.providers.test_motion_dialogue import fake_session
from tests.runtime.test_companion_calls import Caller, runtime_for

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"
PRIMARY = MonitorDescriptor(
    id="PRIMARY", primary=True, rect=ScreenRect(x=0, y=0, width=1920, height=1080),
    work_area=ScreenRect(x=0, y=0, width=1920, height=1040),
)
SECOND = MonitorDescriptor(
    id="SECOND", rect=ScreenRect(x=1920, y=0, width=2560, height=1440),
    work_area=ScreenRect(x=1920, y=0, width=2560, height=1440),
)
RUNNING_GAIT_PX_PER_SEC = 450  # Renderer threshold for its running gait.


def _window(x: int, y: int, width: int, height: int, name: str = "Spotify") -> DesktopNode:
    return DesktopNode.model_construct(
        name=name, offscreen=False, rect=ScreenRect(x=x, y=y, width=width, height=height)
    )


def test_move_contract_keeps_pointer_calls_and_requires_window_reference() -> None:
    assert Move.model_validate({"op": "move", "target": "pointer"}).pace == "walk"
    with pytest.raises(ValidationError):
        Move.model_validate({"op": "move", "target": "window"})
    with pytest.raises(ValidationError):
        Move.model_validate({"op": "move", "target": "pointer", "window": "w1"})
    with pytest.raises(ValidationError):
        Move.model_validate({"op": "move", "target": "screen", "x": 10})  # Never coordinates.
    schema = call_schema({"move"})
    move = schema["$defs"]["Move"]["properties"]
    assert set(move["target"]["enum"]) == {"pointer", "window", "screen"}
    assert set(move["pace"]["enum"]) == {"walk", "run"}


@pytest.mark.asyncio
async def test_core_resolves_semantic_destinations(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT), DeterministicProvider()
    )
    runtime.update_embodiment_topology((PRIMARY, SECOND))

    # On the ground beneath a window on the second monitor: its centre x, that work area's bottom.
    point, where = await runtime._move_destination(
        Move(op="move", target="window", window="w1"), _window(2000, 100, 800, 600)
    )
    assert (point.x, point.y) == (2400, 1439) and where == "the Spotify window"

    # On the primary, the ground is the work area's bottom, above the taskbar.
    point, _ = await runtime._move_destination(
        Move(op="move", target="window", window="w1"), _window(0, 0, 1920, 1080)
    )
    assert (point.x, point.y) == (960, 1039)

    point, where = await runtime._move_destination(
        Move(op="move", target="screen", monitor="primary", place="left"), None
    )
    assert (point.x, point.y) == (288, 1039) and where == "the left of the main monitor"

    # No live pointer here, so the pointer's monitor is the primary and "other" is SECOND.
    point, _ = await runtime._move_destination(
        Move(op="move", target="screen", monitor="other", place="centre"), None
    )
    assert (point.x, point.y) == (1920 + 1280, 1439)

    with pytest.raises(ValueError, match="not on an active display"):
        await runtime._move_destination(
            Move(op="move", target="window", window="w1"), _window(9000, 9000, 100, 100)
        )
    runtime.update_embodiment_topology((PRIMARY,))
    with pytest.raises(ValueError, match="only one monitor"):
        await runtime._move_destination(
            Move(op="move", target="screen", monitor="other"), None
        )


@pytest.mark.asyncio
async def test_run_to_screen_place_then_sit_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    action: dict[str, Any] = {"op": "move", "target": "screen", "monitor": "primary",
                              "place": "right", "pace": "run", "then": "sit"}
    caller = Caller(action)
    runtime, _ = runtime_for(tmp_path, caller)
    await runtime.start()
    assert runtime.app_settings is not None
    runtime.app_settings.provider = caller
    runtime.app_settings.save(SettingsEdit(
        version=8, expected_revision=1, changes={"perception.mode": "image-on-prompt"},
    ))
    session = await fake_session(runtime, monkeypatch)
    queue = runtime.register_embodiment_queue()
    runtime.update_embodiment_topology((PRIMARY,))
    monkeypatch.setattr("sora.runtime.service.capture_application",
                        AsyncMock(side_effect=AssertionError("Moving must not capture")))
    try:
        with owner_local_scope():
            answer = await runtime.dialogue("Run to the right of the screen and sit down")
        command = queue.get_nowait()
        assert command.verb is EmbodimentVerb.MOVE_TO and command.target_point is not None
        assert (command.target_point.x, command.target_point.y) == (1632, 1039)
        assert command.speed_px_per_sec >= RUNNING_GAIT_PX_PER_SEC
        assert await runtime.validate_embodiment_delivery(command)
        # The pose waits for arrival: it becomes the resting state the watch loop restores.
        assert session._resting_state == "sitting"
        assert "run request" in answer and "then sit on arrival" in answer
        assert "not arrival" in answer
    finally:
        await session.close()
        runtime.unregister_embodiment_queue(queue)
        await runtime.close()


def test_walking_pace_uses_the_walking_gait() -> None:
    assert WALK_SPEED_PX_PER_SEC < RUNNING_GAIT_PX_PER_SEC <= RUN_SPEED_PX_PER_SEC


@pytest.mark.asyncio
async def test_turn_resolves_an_issued_window_and_refuses_a_stale_one() -> None:
    tools = CompanionReadTools(check=lambda _: None, observe=AsyncMock())
    tools.windows["w1"] = (_window(100, 100, 400, 300), time.monotonic())
    tools.windows["w2"] = (_window(100, 100, 400, 300), time.monotonic() - 120)

    async def turn(ref: str) -> Any:
        return await collect_reads(
            "Go to that window",
            provider=Caller({"op": "move", "target": "window", "window": ref}),
            tools=tools, check_epoch=lambda: None, file_read=False, desktop_read=True,
            catalogue=None, timeout=2, budget=6000, avatar_control=True,
        )

    fresh = await turn("w1")
    assert fresh.move_window is not None and fresh.action_error is None
    stale = await turn("w2")
    assert stale.move_window is None and "list windows again" in (stale.action_error or "")
