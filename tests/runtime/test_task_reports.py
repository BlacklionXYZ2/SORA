from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sora.contracts.models import ActiveCapabilitySet, TaskStatus
from sora.persistence.records import MessageRecord
from sora.providers.dialogue import DeterministicDialogueProvider
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime

from .helpers import IDENTITY_ROOT, wait_for_status


class _PhrasingProvider(DeterministicDialogueProvider):
    def __init__(self, reply: str | None) -> None:
        super().__init__()
        self.provider_name = "phrasing-fixture"
        self.reply = reply
        self.prompts: list[str] = []

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        self.prompts.append(prompt)
        if self.reply is None:
            raise RuntimeError("model unavailable")
        return self.reply

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        yield await self.respond(prompt, context)


def _runtime(
    root: Path,
    *,
    report: bool = True,
    fault: FaultMode = FaultMode.NONE,
    dialogue: DeterministicDialogueProvider | None = None,
) -> SoraRuntime:
    return SoraRuntime(
        RuntimeConfig(
            root=root,
            identity_root=IDENTITY_ROOT,
            worker_count=1,
            task_timeout_seconds=1,
            lease_seconds=0.2,
            max_attempts=1,
            report_task_outcomes=report,
        ),
        DeterministicProvider(fault=fault),
        dialogue,
    )


async def _reports(runtime: SoraRuntime, task_id: str) -> list[MessageRecord]:
    await runtime.wait_for_task(task_id, timeout=5)
    await runtime.task_reporter.wait_idle()
    messages = await runtime.repository.list_messages(runtime.config.conversation_id)
    return [m for m in messages if m.provenance == f"task report: {task_id}"]


@pytest.mark.asyncio
async def test_completed_task_is_reported_once_in_conversation(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        [report] = await _reports(runtime, receipt.task.task_id)
        assert report.role == "assistant"
        assert " finished: " in report.content
        runtime.task_reporter.schedule(receipt.task.task_id)  # A repeat is ignored.
        assert len(await _reports(runtime, receipt.task.task_id)) == 1
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_task_is_reported_as_not_finished(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, fault=FaultMode.FAILURE)
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=5)
        assert report.status is TaskStatus.FAILED
        [message] = await _reports(runtime, receipt.task.task_id)
        assert " could not finish: " in message.content
        assert " finished: " not in message.content.replace("could not finish", "")
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_reports_are_off_unless_enabled(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, report=False)
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        assert await _reports(runtime, receipt.task.task_id) == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_model_phrases_the_report_and_the_factual_line_is_kept(tmp_path: Path) -> None:
    dialogue = _PhrasingProvider("All done! Here's what came back.")
    runtime = _runtime(tmp_path, dialogue=dialogue)
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        [message] = await _reports(runtime, receipt.task.task_id)
        assert message.content.startswith("All done! Here's what came back.\n\n(")
        assert " finished: " in message.content
        assert "Use only these facts" in dialogue.prompts[-1]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_model_failure_falls_back_to_the_factual_line(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, dialogue=_PhrasingProvider(None))
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        [message] = await _reports(runtime, receipt.task.task_id)
        assert not message.content.startswith("(")
        assert " finished: " in message.content
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancelled_task_is_reported_as_cancelled(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=IDENTITY_ROOT, worker_count=1, task_timeout_seconds=5,
            lease_seconds=0.2, max_attempts=1, report_task_outcomes=True,
        ),
        DeterministicProvider(fault=FaultMode.DELAY, delay_seconds=2),
    )
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Analyze the deterministic fixture.")
        await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING, timeout=3)
        await runtime.cancel(receipt.task.task_id)
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=5)
        assert report.status is TaskStatus.CANCELLED
        [message] = await _reports(runtime, receipt.task.task_id)
        assert message.content.endswith("'s task was cancelled.")
        assert "finished" not in message.content
    finally:
        await runtime.close()
