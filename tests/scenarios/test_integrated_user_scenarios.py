"""P15.4 companion-first conversation and telemetry scenario acceptance."""

from __future__ import annotations

import asyncio
import csv
from pathlib import Path

import pytest
from tests.runtime.helpers import IDENTITY_ROOT, wait_for_status

from sora.contracts.models import NormalizedResult, ProviderOutcome, ProviderRequest, TaskStatus
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime


class TelemetryAnalysisProvider(DeterministicProvider):
    """Fixture specialist that proves it read the two exact user-selected files."""

    def __init__(self, baseline: Path, comparison: Path) -> None:
        super().__init__()
        self.baseline = baseline
        self.comparison = comparison
        self.observed_intent = ""

    @staticmethod
    def _segments(path: Path) -> dict[str, int]:
        with path.open("r", encoding="utf-8", newline="") as stream:
            rows = csv.DictReader(stream)
            return {row["segment"]: int(row["elapsed_ms"]) for row in rows}

    async def _produce(self, request: ProviderRequest) -> NormalizedResult:
        self.observed_intent = request.intent
        assert str(self.baseline) in request.intent
        assert str(self.comparison) in request.intent
        await asyncio.sleep(0.2)
        baseline = self._segments(self.baseline)
        comparison = self._segments(self.comparison)
        deltas = {segment: comparison[segment] - elapsed for segment, elapsed in baseline.items()}
        worst_segment = max(deltas, key=deltas.__getitem__)
        total_delta = sum(deltas.values())
        return NormalizedResult(
            result_id=f"result-{request.run_id}",
            task_id=request.task_id,
            run_id=request.run_id,
            base_revision=0,
            outcome=ProviderOutcome.COMPLETED,
            summary=f"The comparison lap is {total_delta} ms slower.",
            conclusion=(
                f"The comparison lap loses {total_delta} ms; {worst_segment} is the largest "
                f"loss at {deltas[worst_segment]} ms."
            ),
            commands_run=("parse two exact UTF-8 telemetry CSV fixtures",),
        )


@pytest.mark.asyncio
async def test_direct_conversation_does_not_launch_a_specialist(tmp_path: Path) -> None:
    provider = DeterministicProvider()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        provider=provider,
    )
    await runtime.start()
    try:
        reply = await runtime.dialogue("That was an awful lap.")
        assert reply == (
            "SORA is available while background tasks run. You said: That was an awful lap."
        )
        assert runtime.dialogue_status() == "available"
        assert await runtime.active_specialists() == ()
        assert provider.start_count == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_telemetry_analysis_reads_exact_files_while_dialogue_stays_available(
    tmp_path: Path,
) -> None:
    telemetry = tmp_path / "telemetry"
    telemetry.mkdir()
    baseline = telemetry / "baseline.csv"
    comparison = telemetry / "comparison.csv"
    baseline.write_text(
        "segment,elapsed_ms\nsector-1,30000\nsector-2,15000\nsector-3,15000\n",
        encoding="utf-8",
    )
    comparison.write_text(
        "segment,elapsed_ms\nsector-1,30500\nsector-2,15200\nsector-3,17300\n",
        encoding="utf-8",
    )
    provider = TelemetryAnalysisProvider(baseline.resolve(), comparison.resolve())
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            worker_count=1,
            task_timeout_seconds=5,
        ),
        provider=provider,
    )
    await runtime.start()
    try:
        intent = (
            "Compare these two exact telemetry files and identify where the lap loses time: "
            f"{baseline.resolve()} and {comparison.resolve()}"
        )
        receipt = await runtime.submit_task(intent)
        await wait_for_status(runtime, receipt.task.task_id, TaskStatus.REASONING)
        assert runtime.dialogue_status() == "available"
        assert await runtime.active_specialists() == ("deterministic-mock",)
        assert await runtime.dialogue("Are you still with me?") == (
            "SORA is available while background tasks run. You said: Are you still with me?"
        )

        report = await runtime.wait_for_task(receipt.task.task_id, timeout=5)
        assert report.status is TaskStatus.COMPLETED
        assert report.result is not None
        assert report.result.summary == "The comparison lap is 3000 ms slower."
        assert report.result.conclusion == (
            "The comparison lap loses 3000 ms; sector-3 is the largest loss at 2300 ms."
        )
        assert provider.observed_intent == intent
        assert await runtime.active_specialists() == ()
    finally:
        await runtime.close()
