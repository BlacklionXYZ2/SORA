"""Tool families: what the decision layer chooses between, and the operations each one unlocks.

A family groups companion operations that serve one kind of request. The descriptions are what
native Laya reads, phrased as "Does answering this message need <description>?". Families can
depend on others' operations (pointing at a control needs the window list first).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    name: str
    description: str
    operations: frozenset[str]


FAMILIES: tuple[Family, ...] = (
    Family("windows",
           "reading open windows, the current app, or text and controls inside an application",
           frozenset({"list_windows", "inspect_window"})),
    Family("files", "listing, searching or reading files and folders on this PC",
           frozenset({"list_files", "search_files", "read_file"})),
    Family("memory", "recalling or showing something remembered about the owner",
           frozenset({"find_memory", "present_memory"})),
    Family("motion", "moving SORA's 3D avatar: walking, running, sitting",
           frozenset({"pose", "move", "list_windows"})),  # "go to the Spotify window"
    Family("indicate", "SORA's avatar looking at or pointing to a control in a window",
           frozenset({"look", "point", "list_windows", "inspect_window"})),
    Family("delegate",
           "handing work to an agent (Cody, Hermes, Aggie, Claude or a custom agent) or "
           "writing code or files",
           frozenset({"list_agents", "delegate"})),
    Family("view_window",
           "looking closely at a window's picture to read small details or an error",
           frozenset({"view_window", "list_windows"})),
)
BY_NAME = {family.name: family for family in FAMILIES}


def allowed_operations(families: Iterable[str]) -> frozenset[str]:
    """The operations the brain may be offered when these families are chosen.

    finish is always allowed, and so are remember and remember_thought: deciding what is worth
    keeping is her initiative, not something the owner's message has to call for.
    """
    allowed = {"finish", "remember", "remember_thought"}
    for name in families:
        family = BY_NAME.get(name)
        if family is not None:
            allowed |= family.operations
    return frozenset(allowed)


def laya_questions(
    families: Iterable[Family] = FAMILIES, *, agent_names: Iterable[str] = (),
) -> dict[str, object]:
    """One yes/no question per family, asked as a two-option choice.

    The delegate question names the owner's agents, nicknames included: untrained Laya missed
    "Ask Pip to check my packing list" when only the built-in names were listed.

    Laya's own ``noul`` type can follow its option labels rather than the text on the English
    checkpoint (upstream issue #156), so yes/no is asked as a neutral A/B choice instead.
    """
    names = [name for name in dict.fromkeys(agent_names) if name.strip()][:12]

    def described(family: Family) -> str:
        if family.name == "delegate" and names:
            return ("handing work to an agent (" + ", ".join(names)
                    + ") or writing code or files")
        return family.description

    return {
        family.name: {
            "type": "choice",
            "instructions": f"Does answering this message need {described(family)}?",
            "criteria": {"A": "yes, it needs that", "B": "no, it does not"},
        }
        for family in families
    }
