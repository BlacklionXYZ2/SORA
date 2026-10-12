"""Reflection: SORA reviews her recent memories against her goals and her character.

This is where her goals change (owner decision, 2026-10-09: her character is fixed, her goals are
hers). She is shown her character, her active goals with recent progress, and the memories made
since her last reflection, each with an issued reference (g1, m1, ...). She may:

  note_goal         record progress towards a goal, linked to the memories it comes from;
  add_goal          start a goal of her own;
  revise_goal       reword a goal, with a reason;
  close_goal        end a goal as achieved or dropped, with a reason (history is kept);
  remember_thought  keep an insight as one of her own memories.

Small models are kept honest by construction: references are issued by Core and checked; goals
end rather than vanish; her changes are rate-limited (sora.runtime.goals); every step is traced.
Staying true to her character comes from the character text in front of her now, and later from
training on the owner's corrections.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sora.contracts.companion_call import (
    AddGoal,
    CloseGoal,
    CompanionCall,
    NoteGoal,
    RememberThought,
    ReviseGoal,
)
from sora.contracts.companion_read import FinishRead
from sora.persistence.records import MemoryState
from sora.persistence.repository import SoraRepository
from sora.providers.dialogue import CompanionCallProvider
from sora.runtime.goals import GoalError, GoalStore
from sora.runtime.self_memory import memory_label, remember_own_thought

OPERATIONS = frozenset({"note_goal", "add_goal", "revise_goal", "close_goal",
                        "remember_thought"})
MAX_STEPS = 8
MAX_MEMORIES = 30

REFLECTION_PROMPT = """Reflect, as yourself. This is your private time to think, not a reply to
the owner. Below are your character, your goals and what you have remembered since you last
reflected.
- If a memory shows progress towards one of your goals, note_goal it with that memory's target.
- If something now matters to you that none of your goals covers, add_goal (in your own voice).
- Revise a goal that has changed shape, or close one you achieved or no longer want, with an
  honest reason. Goals are yours; keep them true to your character, few and meaningful.
- Keep a real insight about yourself with remember_thought.
Make only the changes that matter, then finish. Doing nothing is fine."""


@dataclass
class Reflection:
    started_at: datetime
    memories_seen: int
    goals_seen: int
    actions: list[dict[str, Any]] = field(default_factory=list)


async def reflect(
    provider: CompanionCallProvider,
    *,
    repository: SoraRepository,
    goals: GoalStore,
    owner_id: str,
    project_id: str | None,
    character: str,
    since: datetime | None,
    captures: Path,
    provider_name: str,
    model: str | None,
) -> Reflection:
    now = datetime.now(UTC)
    since = since or now - timedelta(days=7)
    memories = [
        m for m in await repository.list_memories(owner_id, project_id=project_id,
                                                  observed_at=now)
        if m.state == MemoryState.ACTIVE and m.created_at is not None and m.created_at >= since
    ][-MAX_MEMORIES:]
    memory_refs = {f"m{i}": m for i, m in enumerate(memories, 1)}
    active = await goals.goals()
    goal_refs = {f"g{i}": g for i, g in enumerate(active, 1)}
    report = Reflection(now, len(memories), len(active))
    records: list[dict[str, Any]] = [
        {"operation": "my_character", "data": {"text": character[:4000]}},
        {"operation": "my_goals", "data": {"goals": [
            {"target": ref, "goal": g.text, "why": g.why,
             "started": f"{g.created_at:%d %b %Y}",
             "recent_progress": [e.text for e in g.events if e.kind == "progress"][-3:]}
            for ref, g in goal_refs.items()]}},
        {"operation": "memories_since_last_reflection", "data": {"memories": [
            {"target": ref, "whose": memory_label(m), "text": m.content[:300]}
            for ref, m in memory_refs.items()]}},
    ]
    for _ in range(MAX_STEPS):
        observations = "Reflection\n" + json.dumps(records, ensure_ascii=False)
        try:
            call = CompanionCall.model_validate(
                await provider.choose_call(REFLECTION_PROMPT, observations, OPERATIONS))
        except Exception as exc:  # an invalid call ends reflection; nothing half-done
            report.actions.append({"op": "invalid", "reason": str(exc)[:200]})
            break
        action = call.root
        if isinstance(action, FinishRead):
            break
        outcome: dict[str, Any] = {"op": action.op}
        try:
            if isinstance(action, AddGoal):
                goal = await goals.add(action.text, action.why, actor="sora")
                goal_refs[f"g{len(goal_refs) + 1}"] = goal
                outcome |= {"status": "ok", "goal": goal.text}
            elif isinstance(action, ReviseGoal):
                goal = await goals.revise(_goal(goal_refs, action.target).goal_id, action.text,
                                          action.reason, actor="sora")
                outcome |= {"status": "ok", "goal": goal.text}
            elif isinstance(action, CloseGoal):
                goal = await goals.close(_goal(goal_refs, action.target).goal_id,
                                         action.outcome, action.reason, actor="sora")
                outcome |= {"status": "ok", "goal": goal.text, "outcome": action.outcome}
            elif isinstance(action, NoteGoal):
                unknown = [m for m in action.memories if m not in memory_refs]
                if unknown:
                    raise GoalError(f"Unknown memory reference {unknown[0]}")
                goal = await goals.note(
                    _goal(goal_refs, action.target).goal_id, action.text,
                    tuple(memory_refs[m].memory_id for m in action.memories), actor="sora")
                outcome |= {"status": "ok", "goal": goal.text}
            elif isinstance(action, RememberThought):
                stored = await remember_own_thought(
                    repository, thought=action.thought, owner_text="(reflection)",
                    reply="", owner_id=owner_id, project_id=project_id,
                    provider=provider_name, model=model, captures=captures)
                outcome |= {"status": "ok" if stored else "already remembered"}
            else:
                outcome |= {"status": "unsupported", "reason": "Not a reflection operation"}
        except GoalError as exc:
            outcome |= {"status": "refused", "reason": str(exc)}
        report.actions.append(outcome)
        records.append({"operation": action.op, "data": outcome})
    return report


def _goal(refs: dict[str, Any], target: str) -> Any:
    goal = refs.get(target)
    if goal is None:
        raise GoalError(f"Unknown goal reference {target}")
    return goal
