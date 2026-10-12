"""Pace and arrival pose come from the owner's words, not the model's habits."""

from __future__ import annotations

import pytest

from sora.contracts.companion_call import Move
from sora.runtime.move_intent import owner_move


@pytest.mark.parametrize("text,model,expected", [
    # Seen live on E4B (2026-10-08): "run" sent as walk.
    ("Run over to the other side of the screen and sit.", {"pace": "walk", "then": "sit"},
     ("run", "sit")),
    # Seen live: an arrival pose nobody asked for (it was a wave, since removed).
    ("Go over to the Antigravity window.", {"pace": "walk", "then": "lean"}, ("walk", None)),
    ("Come here", {"pace": "run"}, ("walk", None)),
    ("Hurry to the left and sit down", {}, ("run", "sit")),
    # The owner asked for a pose the model left out.
    ("Walk to Spotify and lean on it", {}, ("walk", "lean")),
    # There is no wave pose any more: waving words choose no arrival pose.
    ("Walk to Spotify and wave at me", {}, ("walk", None)),
    # Two poses named: no guessing which comes on arrival.
    ("Walk over, sit or stand, your choice", {}, ("walk", None)),
])
def test_owner_words_set_pace_and_arrival_pose(
    text: str, model: dict[str, object], expected: tuple[str, str | None],
) -> None:
    move = owner_move(Move.model_validate({"op": "move", "target": "pointer", **model}), text)
    assert (move.pace, move.then) == expected
    assert move.target == "pointer"


def test_the_other_side_is_relative_to_where_she_stands() -> None:
    from sora.contracts.embodiment import MonitorDescriptor, ScreenRect, VirtualDesktopPoint
    from sora.runtime.move_intent import other_side, wants_other_side

    main = MonitorDescriptor(
        id="main", primary=True, rect=ScreenRect(x=0, y=0, width=3840, height=2160),
    )
    side = MonitorDescriptor(id="side", rect=ScreenRect(x=-1280, y=813, width=1280, height=1024))
    monitors = (side, main)
    assert wants_other_side("Run over to the other side of the screen and sit.")
    assert wants_other_side("walk across the screen")
    assert not wants_other_side("come to my side")
    assert other_side(monitors, VirtualDesktopPoint(x=90, y=2000)) == (main, "right")
    assert other_side(monitors, VirtualDesktopPoint(x=3500, y=2000)) == (main, "left")
    assert other_side(monitors, VirtualDesktopPoint(x=-1100, y=1800)) == (side, "right")
    assert other_side(monitors, VirtualDesktopPoint(x=-5000, y=0)) is None
