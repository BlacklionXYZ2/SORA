"""Typed "cancel that task" cancels the one running task; ambiguity asks; chat stays chat."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from sora.contracts.models import TaskStatus
from sora.routing import RoutingEngine
from sora.runtime.chat_cancel import cancel_from_chat


def task(task_id: str, backend: str, status: TaskStatus = TaskStatus.REASONING) -> Any:
    return SimpleNamespace(task_id=task_id, status=status, effective_backend=backend,
                           requested_backend=backend)


async def run(text: str, records: list[Any]) -> tuple[str | None, list[str]]:
    engine = RoutingEngine()
    cancelled: list[str] = []

    async def tasks() -> list[Any]:
        return records

    async def cancel(task_id: str) -> bool:
        cancelled.append(task_id)
        return True

    reply = await cancel_from_chat(
        text, tasks=tasks, choose=engine.disambiguate_steering,
        mentioned=engine.agent_names.mentioned, name_for=engine.agent_names.name_for,
        cancel=cancel,
    )
    return reply, cancelled


@pytest.mark.asyncio
async def test_cancel_that_task_with_one_running_task() -> None:
    # Seen live 2026-10-08: the model asked which task, though only one was running.
    reply, cancelled = await run("Actually, cancel that task.", [
        task("task-done", "codex", TaskStatus.COMPLETED), task("task-1", "hermes"),
    ])
    assert cancelled == ["task-1"]
    assert reply is not None and reply.startswith("I've asked Hermes to stop.")
    assert "not yet confirmed" in reply


@pytest.mark.asyncio
async def test_naming_the_agent_picks_its_task_and_ambiguity_asks() -> None:
    records = [task("task-1", "hermes"), task("task-2", "codex")]
    reply, cancelled = await run("Cancel Cody's task please", records)
    assert cancelled == ["task-2"] and reply is not None and "Cody" in reply
    reply, cancelled = await run("cancel that", records)
    assert cancelled == [] and reply is not None and reply.startswith("Which task")


@pytest.mark.parametrize("text", [
    "Don't cancel it, let it finish.",
    "How do I cancel a subscription?",  # no running task: ordinary chat below
    "Stop being silly",
    "What's the weather like?",
])
@pytest.mark.asyncio
async def test_ordinary_chat_is_left_to_the_conversation(text: str) -> None:
    records = [] if "subscription" in text else [task("task-1", "hermes")]
    reply, cancelled = await run(text, records)
    assert reply is None and cancelled == []
