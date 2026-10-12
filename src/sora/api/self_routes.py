"""Owner-local routes for SORA's self: her goals, and asking her to reflect now.

    GET  /api/v1/self/goals    active and closed goals with dates and history
    POST /api/v1/self/reflect  run one reflection now; returns what she did
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sora.api.protocol import HttpRequest, HttpResponse
from sora.security.local_policy import is_owner_local

if TYPE_CHECKING:
    from sora.runtime.service import SoraRuntime


async def handle_self(runtime: SoraRuntime, request: HttpRequest, path: str) -> HttpResponse:
    if not is_owner_local():
        return HttpResponse.error(403, "SORA's self is owner-local only", code="FORBIDDEN")
    if path == "/api/v1/self/goals" and request.method == "GET":
        goals = await runtime.goal_store().goals(include_closed=True)
        return HttpResponse.json({"goals": [
            {"goal_id": g.goal_id, "text": g.text, "why": g.why, "origin": g.origin,
             "status": g.status, "created_at": g.created_at.isoformat(),
             "updated_at": g.updated_at.isoformat(),
             "closed_at": g.closed_at.isoformat() if g.closed_at else None,
             "close_reason": g.close_reason,
             "history": [{"kind": e.kind, "text": e.text, "reason": e.reason,
                          "actor": e.actor, "memory_ids": list(e.memory_ids),
                          "at": e.occurred_at.isoformat()} for e in g.events]}
            for g in goals]})
    if path == "/api/v1/self/reflect" and request.method == "POST":
        try:
            reflection = await runtime.reflect_now()
        except (RuntimeError, ValueError) as exc:
            return HttpResponse.error(409, str(exc), code="REFLECTION_UNAVAILABLE")
        return HttpResponse.json({"started_at": reflection.started_at.isoformat(),
                                  "memories_seen": reflection.memories_seen,
                                  "goals_seen": reflection.goals_seen,
                                  "actions": reflection.actions})
    return HttpResponse.error(404, "Unknown self route", code="NOT_FOUND")
