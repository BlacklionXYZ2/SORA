"""Cancelling an agent's task from typed chat, decided by Core rather than the model.

Voice already treats "cancel that task" as a control phrase (sora.voice.intents). Typed chat sent
it to the model, which asked which task was meant and cancelled nothing, although only one task
was running. Here an explicit cancel request naming an agent, or referring to "that"/"the task"
while exactly one task runs, cancels it. Anything ambiguous is asked about, and plain chat that
merely contains "stop" is left to the conversation.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from sora.contracts.models import TaskStatus

_CANCEL = re.compile(r"\b(?:cancel|abort)\b|\bstop\b.*\b(?:task|job|run|working)\b", re.I)
_NEGATED = re.compile(r"\b(?:don'?t|do not|never|no need to|not)\b[^.?!]*\b(?:cancel|abort|stop)\b",
                      re.I)
_TASK_WORDS = re.compile(r"\b(?:task|job|run|that|it|this|him|her|them)\b", re.I)
_ACTIVE = {TaskStatus.QUEUED, TaskStatus.ROUTING, TaskStatus.REASONING, TaskStatus.WORKING}


async def cancel_from_chat(
    text: str,
    *,
    tasks: Callable[[], Awaitable[Sequence[Any]]],
    choose: Callable[[str, Sequence[Any]], str | None],
    mentioned: Callable[[str], Sequence[str]],
    name_for: Callable[[str | None], str | None],
    cancel: Callable[[str], Awaitable[bool]],
) -> str | None:
    """A reply when this message is a cancel request, otherwise None (ordinary chat)."""
    if not _CANCEL.search(text) or _NEGATED.search(text):
        return None
    if not (mentioned(text) or _TASK_WORDS.search(text)):
        return None
    records = await tasks()
    running = [task for task in records if getattr(task, "status", None) in _ACTIVE]
    if not running:
        return None  # nothing to cancel: let the conversation answer
    task_id = choose(text, records)
    if task_id is None:
        return "Which task should I cancel? More than one is running; name the agent."
    task = next(task for task in running if task.task_id == task_id)
    agent = name_for(task.effective_backend or task.requested_backend) or "the agent"
    if not await cancel(task_id):
        return f"{agent}'s task had already finished, so there was nothing to cancel."
    return (
        f"I've asked {agent} to stop. Cancellation is requested, not yet confirmed; "
        f"Activity shows when it has ended. (Task {task_id}.)"
    )
