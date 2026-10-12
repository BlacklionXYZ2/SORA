"""The owner's own words decide how SORA's avatar moves, not the model's guess.

Small models fill a move call's optional fields from habit: E4B sent "run to the other side"
as a walk, and added a wave on arrival that nobody asked for. Pace and the arrival pose are
taken from the owner's message; the model still chooses the destination.
"""

from __future__ import annotations

import re

from sora.contracts.companion_call import Move
from sora.contracts.embodiment import MonitorDescriptor, VirtualDesktopPoint

_RUN = re.compile(r"\b(run|running|ran|hurry|quick|quickly|fast|dash|sprint|rush)\b", re.I)
_POSES = {
    "sit": re.compile(r"\bsit(s|ting)?\b|\btake a seat\b", re.I),
    "lean": re.compile(r"\blean(s|ing)?\b", re.I),
    "climb": re.compile(r"\bclimb(s|ing)?\b", re.I),
    "stand": re.compile(r"\bstand(s|ing)?\b", re.I),
}


_OTHER_SIDE = re.compile(r"\b(other|opposite|far) side\b|\bacross the screen\b", re.I)


def wants_other_side(owner_text: str) -> bool:
    return bool(_OTHER_SIDE.search(owner_text))


def other_side(
    monitors: tuple[MonitorDescriptor, ...], position: VirtualDesktopPoint,
) -> tuple[MonitorDescriptor, str] | None:
    """The far side of the monitor SORA stands on: "the other side" is relative to her."""
    monitor = next((m for m in monitors if m.rect.contains(position.x, position.y)), None)
    if monitor is None:
        return None
    left_half = position.x < monitor.rect.x + monitor.rect.width / 2
    return monitor, "right" if left_half else "left"


def owner_move(move: Move, owner_text: str) -> Move:
    """Keep the model's destination; take pace and the arrival pose from the owner's words."""
    pace = "run" if _RUN.search(owner_text) else "walk"
    then = move.then if move.then is not None and _POSES[move.then].search(owner_text) else None
    if then is None:
        asked = [name for name, pattern in _POSES.items() if pattern.search(owner_text)]
        then = asked[0] if len(asked) == 1 else None  # type: ignore[assignment]
    return move.model_copy(update={"pace": pace, "then": then})
