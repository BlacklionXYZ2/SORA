"""SORA's goals: hers to add, revise, close and note progress on, with dates and full history.

Owner decisions (2026-10-09):
- her character is fixed (identity/, written by the owner); her goals are hers to change;
- goals carry when they started and last changed; a closed goal keeps its start and end dates;
- in reflection she may record what she did towards a goal, drawn from her memories.

Goals end rather than vanish: ``achieved`` or ``dropped``, each with a reason. Every change is
a ``goal_events`` row, so the history of what she wanted, and why it changed, is kept. The
database is the authority; ``<state>/self/goals.md`` is regenerated after each change for the
owner to read. The owner's changes are never rate-limited; hers are, so a confused turn cannot
churn her goals.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from sora.persistence.repository import SoraRepository

Actor = Literal["sora", "owner"]
MAX_ACTIVE = 12
SORA_CHANGES_PER_DAY = 10


@dataclass(frozen=True)
class GoalEvent:
    kind: str
    text: str
    reason: str
    actor: str
    memory_ids: tuple[str, ...]
    occurred_at: datetime


@dataclass(frozen=True)
class Goal:
    goal_id: str
    text: str
    why: str
    origin: str
    status: str
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None
    close_reason: str | None
    entity_version: int
    events: tuple[GoalEvent, ...] = field(default=())


class GoalError(ValueError):
    pass


class GoalStore:
    def __init__(self, repository: SoraRepository, owner_id: str, self_folder: Path) -> None:
        self.repository = repository
        self.owner_id = owner_id
        self.self_folder = self_folder

    # ---- reading ---------------------------------------------------------------------------

    async def goals(self, *, include_closed: bool = False) -> list[Goal]:
        def read(db: sqlite3.Connection) -> list[Goal]:
            rows = db.execute(
                "SELECT * FROM goals WHERE owner_id=?" + ("" if include_closed else
                                                           " AND status='active'")
                + " ORDER BY created_at", (self.owner_id,)).fetchall()
            result = []
            for row in rows:
                events = tuple(
                    GoalEvent(e["kind"], e["text"], e["reason"], e["actor"],
                              tuple(json.loads(e["memory_ids"])),
                              datetime.fromisoformat(e["occurred_at"]))
                    for e in db.execute("SELECT * FROM goal_events WHERE goal_id=? "
                                        "ORDER BY occurred_at, rowid", (row["goal_id"],)))
                result.append(Goal(
                    row["goal_id"], row["text"], row["why"], row["origin"], row["status"],
                    datetime.fromisoformat(row["created_at"]),
                    datetime.fromisoformat(row["updated_at"]),
                    datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
                    row["close_reason"], row["entity_version"], events))
            return result

        return await self.repository.database.read(read)

    # ---- changing --------------------------------------------------------------------------

    async def add(self, text: str, why: str, *, actor: Actor) -> Goal:
        text, why = _clean(text, 200, "goal"), _clean(why, 300, "reason")
        now = datetime.now(UTC)
        goal_id = f"goal-{uuid.uuid4()}"

        def write(db: sqlite3.Connection) -> None:
            self._limit(db, actor, now)
            active = db.execute("SELECT text FROM goals WHERE owner_id=? AND status='active'",
                                (self.owner_id,)).fetchall()
            if len(active) >= MAX_ACTIVE:
                raise GoalError(f"Already {MAX_ACTIVE} active goals; close one first")
            if any(row["text"].casefold() == text.casefold() for row in active):
                raise GoalError("That goal is already active")
            db.execute("INSERT INTO goals VALUES (?, ?, ?, ?, ?, 'active', ?, ?, NULL, NULL, 1)",
                       (goal_id, self.owner_id, text, why, actor, now.isoformat(),
                        now.isoformat()))
            self._event(db, goal_id, "added", text, why, actor, (), now)

        await self.repository.database.write(write)
        return await self._changed(goal_id)

    async def revise(self, goal_id: str, text: str, reason: str, *, actor: Actor) -> Goal:
        text, reason = _clean(text, 200, "goal"), _clean(reason, 300, "reason")
        return await self._update(goal_id, actor, "revised", text, reason,
                                  "UPDATE goals SET text=?, updated_at=?, "
                                  "entity_version=entity_version+1 WHERE goal_id=?", (text,))

    async def close(self, goal_id: str, outcome: Literal["achieved", "dropped"], reason: str,
                    *, actor: Actor) -> Goal:
        reason = _clean(reason, 300, "reason")
        now = datetime.now(UTC).isoformat()
        return await self._update(goal_id, actor, outcome, "", reason,
                                  "UPDATE goals SET status=?, closed_at=?, close_reason=?, "
                                  "updated_at=?, entity_version=entity_version+1 "
                                  "WHERE goal_id=?", (outcome, now, reason))

    async def note(self, goal_id: str, text: str, memory_ids: tuple[str, ...], *,
                   actor: Actor) -> Goal:
        """Progress: what was done towards the goal, linked to the memories it comes from."""
        text = _clean(text, 300, "progress note")
        return await self._update(goal_id, actor, "progress", text, "", None, (),
                                  memory_ids=memory_ids[:8])

    async def _update(self, goal_id: str, actor: Actor, kind: str, text: str, reason: str,
                      statement: str | None, values: tuple[object, ...], *,
                      memory_ids: tuple[str, ...] = ()) -> Goal:
        now = datetime.now(UTC)

        def write(db: sqlite3.Connection) -> None:
            row = db.execute("SELECT status FROM goals WHERE goal_id=? AND owner_id=?",
                             (goal_id, self.owner_id)).fetchone()
            if row is None:
                raise GoalError("No such goal")
            if row["status"] != "active":
                raise GoalError("That goal is already closed")
            self._limit(db, actor, now)
            if statement is not None:
                db.execute(statement, (*values, now.isoformat(), goal_id))
            else:
                db.execute("UPDATE goals SET updated_at=? WHERE goal_id=?",
                           (now.isoformat(), goal_id))
            self._event(db, goal_id, kind, text, reason, actor, memory_ids, now)

        await self.repository.database.write(write)
        return await self._changed(goal_id)

    def _limit(self, db: sqlite3.Connection, actor: Actor, now: datetime) -> None:
        if actor != "sora":
            return
        since = (now - timedelta(days=1)).isoformat()
        count = db.execute(
            "SELECT COUNT(*) FROM goal_events e JOIN goals g ON g.goal_id=e.goal_id "
            "WHERE g.owner_id=? AND e.actor='sora' AND e.occurred_at>=?",
            (self.owner_id, since)).fetchone()[0]
        if count >= SORA_CHANGES_PER_DAY:
            raise GoalError("Enough goal changes for today; reflect again tomorrow")

    def _event(self, db: sqlite3.Connection, goal_id: str, kind: str, text: str, reason: str,
               actor: Actor, memory_ids: tuple[str, ...], now: datetime) -> None:
        db.execute("INSERT INTO goal_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                   (f"goal-event-{uuid.uuid4()}", goal_id, kind, text, reason, actor,
                    json.dumps(list(memory_ids)), now.isoformat()))
        revision = SoraRepository._next_revision(db)
        SoraRepository._append_event(db, self.owner_id, revision, f"goal.{kind}", None, None,
                                     {"goal_id": goal_id, "actor": actor})

    async def _changed(self, goal_id: str) -> Goal:
        goals = await self.goals(include_closed=True)
        try:
            self.write_markdown(goals)
        except OSError:
            pass  # the readable copy never blocks a change
        return next(goal for goal in goals if goal.goal_id == goal_id)

    # ---- the owner's readable copy ---------------------------------------------------------

    def write_markdown(self, goals: list[Goal]) -> Path:
        self.self_folder.mkdir(parents=True, exist_ok=True)
        lines = ["# SORA's goals", "",
                 "Generated by SORA's Core from her goals; edits here are not read back yet.", ""]
        active = [g for g in goals if g.status == "active"]
        closed = [g for g in goals if g.status != "active"]
        lines += ["## Active", ""] if active else ["## Active", "", "None yet.", ""]
        for goal in active:
            lines += [f"### {goal.text}", "",
                      f"- Started {_day(goal.created_at)}"
                      + (f", last changed {_day(goal.updated_at)}"
                         if goal.updated_at.date() != goal.created_at.date() else ""),
                      f"- Why: {goal.why}"]
            for event in goal.events:
                if event.kind == "progress":
                    lines.append(f"- {_day(event.occurred_at)}: {event.text}")
                elif event.kind == "revised":
                    lines.append(f"- Revised {_day(event.occurred_at)}: {event.reason}")
            lines.append("")
        if closed:
            lines += ["## Closed", ""]
            for goal in closed:
                lines.append(f"- **{goal.text}**: {goal.status} "
                             f"({_day(goal.created_at)} to "
                             f"{_day(goal.closed_at) if goal.closed_at else '?'}): "
                             f"{goal.close_reason}")
        target = self.self_folder / "goals.md"
        target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return target


def _clean(value: str, limit: int, what: str) -> str:
    value = " ".join(value.split())
    if not 3 <= len(value) <= limit:
        raise GoalError(f"The {what} must be 3-{limit} characters")
    return value


def _day(moment: datetime) -> str:
    return f"{moment.astimezone(UTC):%d %b %Y}"
