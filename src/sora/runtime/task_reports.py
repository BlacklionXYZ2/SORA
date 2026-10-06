"""SORA tells the owner in conversation when delegated work finishes (V1 acceptance step 6)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sora.contracts.models import NormalizedResult, TaskRecord, TaskStatus
from sora.persistence.records import MessageRecord

if TYPE_CHECKING:
    from sora.runtime.service import SoraRuntime

_OUTCOME = {
    TaskStatus.COMPLETED: "finished",
    TaskStatus.FAILED: "could not finish",
    TaskStatus.CANCELLED: "was cancelled",
}
_FACTS_LIMIT = 400
_PHRASING_TIMEOUT_SECONDS = 45.0


def _one_line(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _facts(task: TaskRecord, result: NormalizedResult | None) -> str:
    if task.status is TaskStatus.CANCELLED:
        return "Cancelled before a result was accepted."
    if result is None:
        return "No result was recorded."
    if task.status is TaskStatus.FAILED and result.error is not None:
        return _one_line(result.error.message, _FACTS_LIMIT)
    return _one_line(result.conclusion or result.summary, _FACTS_LIMIT)


class TaskReporter:
    """Post one assistant message per finished task, phrased by SORA when her model can.

    The local model words the report in her voice, but only from Core-verified facts, and a
    factual footer is always kept so a small model cannot misstate the outcome unnoticed.
    """

    def __init__(self, runtime: SoraRuntime) -> None:
        self._runtime = runtime
        self._pending: set[asyncio.Task[None]] = set()
        self._reported: set[str] = set()

    def schedule(self, task_id: str) -> None:
        if task_id in self._reported:
            return
        self._reported.add(task_id)
        job = asyncio.create_task(self._report_safely(task_id))
        self._pending.add(job)
        job.add_done_callback(self._pending.discard)

    async def close(self, *, grace_seconds: float = 5.0) -> None:
        """Let in-flight reports finish briefly, then cancel the rest."""
        if self._pending:
            await asyncio.wait(tuple(self._pending), timeout=grace_seconds)
        for job in tuple(self._pending):
            job.cancel()
        await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    async def wait_idle(self) -> None:
        """Test hook: wait for every scheduled report to be written."""
        await asyncio.gather(*tuple(self._pending), return_exceptions=True)

    async def _report_safely(self, task_id: str) -> None:
        try:
            await self.report(task_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # A failed report must never affect the task itself.
            await self._runtime.runtime_repository.record_trace(
                correlation_id=task_id,
                phase="task.report_failed",
                now=datetime.now(UTC),
                task_id=task_id,
                fields={"error": type(exc).__name__},
                secrets=self._runtime.config.secrets,
            )

    async def report(self, task_id: str) -> MessageRecord | None:
        runtime = self._runtime
        task = await runtime.runtime_repository.get_task(task_id)
        if task is None or task.status not in _OUTCOME:
            return None
        result = await runtime.runtime_repository.result_for_task(task_id)
        names = runtime.routing_engine.agent_names
        agent = names.name_for(task.effective_backend or task.requested_backend) or "Your agent"
        outcome = _OUTCOME[task.status]
        facts = _facts(task, result)
        footer = (f"{agent}'s task was cancelled." if task.status is TaskStatus.CANCELLED
                  else f"{agent} {outcome}: {facts}")
        phrased = await self._phrase(task, agent, outcome, facts)
        message = MessageRecord(
            message_id=f"message-{uuid.uuid4()}",
            conversation_id=runtime.config.conversation_id,
            owner_id=runtime.config.owner_id,
            project_id=runtime.config.project_id,
            role="assistant",
            content=f"{phrased}\n\n({footer})" if phrased else footer,
            provenance=f"task report: {task.task_id}",
            created_at=datetime.now(UTC),
        )
        await runtime.repository.append_message(message)
        return message

    async def _phrase(
        self, task: TaskRecord, agent: str, outcome: str, facts: str
    ) -> str | None:
        provider = self._runtime.dialogue_provider
        if getattr(provider, "provider_name", "") == "deterministic":
            return None
        brief = task.companion_brief
        request = f"Request: {_one_line(brief, 300)}\n" if brief else ""
        prompt = (
            "[TASK REPORT - Core-verified facts]\n"
            f"Agent: {agent}\nOutcome: {outcome}\n{request}Result: {facts}\n"
            "Tell the owner about this in one or two short sentences, in your own voice. "
            "Use only these facts. Do not add details, and do not call it a success unless "
            "the outcome is 'finished'."
        )
        try:
            context, _ = await self._runtime._direct_dialogue_context(
                prompt, allow_task_context=False
            )
            text = await asyncio.wait_for(
                provider.respond(prompt, context), timeout=_PHRASING_TIMEOUT_SECONDS
            )
        except Exception:  # Unavailable or slow model: fall back to the factual line.
            return None
        text = text.strip()
        return text or None
