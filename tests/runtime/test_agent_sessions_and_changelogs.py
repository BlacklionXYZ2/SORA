"""Lasting agent sessions, and the agent-authored changelog Core verifies."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderRequest,
)
from sora.providers.base import ProviderLaunchError, ReasoningProvider
from sora.providers.mock import DeterministicProvider
from sora.routing.router import RoutingEngine
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


ENTRY_NAME = "changelog/20260929T120000_session-work_ANTIGRAVITY.md"


class SpyProvider:
    """A provider that records launches, resumes, and acts like an agent about its changelog."""

    def __init__(
        self,
        name: str,
        *,
        resume_fails: bool = False,
        cwd: Path | None = None,
        entry_body: str | None = None,
        entry_text: str | None = None,
        reported_path: str | None = None,
        session_id_override: str | None = None,
        result_error: str | None = None,
    ) -> None:
        self.name = name
        self.resume_fails = resume_fails
        self.cwd = str(cwd) if cwd is not None else None
        self.entry_body = entry_body
        self.entry_text = entry_text
        self.reported_path = reported_path
        self.session_id_override = session_id_override
        self.result_error = result_error
        self.started: list[str] = []
        self.resumed: list[str] = []
        self._requests: dict[str, ProviderRequest] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name, sessions=True, resume=True, cancel=True,
        )

    async def start(self, request: ProviderRequest) -> str:
        self.started.append(request.run_id)
        self._requests[request.run_id] = request
        return request.run_id

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        self.resumed.append(session_id)
        if self.resume_fails:
            raise ProviderLaunchError(ProviderErrorCode.UNAVAILABLE, "session expired")
        return await self.start(request)

    async def result(self, run_id: str) -> NormalizedResult:
        if self.result_error is not None:
            raise ValueError(self.result_error)
        request = self._requests.get(run_id)
        task_id = request.task_id if request is not None else "task-1"
        reported = self.reported_path
        if self.entry_body is not None and self.cwd is not None:
            # The agent writes its own entry before finishing, exactly as the prompt requires.
            target = Path(self.cwd) / ENTRY_NAME
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.entry_body, encoding="utf-8")
            reported = ENTRY_NAME if reported is None else reported
        return NormalizedResult(
            result_id=f"result-{run_id}",
            task_id=task_id,
            run_id=run_id,
            base_revision=0,
            outcome=ProviderOutcome.COMPLETED,
            summary=f"Work completed by {self.name}",
            conclusion=f"Completed with {self.name}",
            changelog_path=reported,
            changelog_entry=self.entry_text,
        )

    async def steer(self, run_id: str, instruction: str) -> None:
        raise NotImplementedError("steering unsupported")

    async def cancel(self, run_id: str) -> None:
        pass

    async def status(self, run_id: str) -> str:
        return "completed"

    async def session_id(self, run_id: str) -> str | None:
        if self.session_id_override is not None:
            return self.session_id_override
        return f"session-{run_id}"

    async def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        if False:
            yield EventEnvelope.model_construct()


def make_runtime(
    tmp_path: Path,
    provider: SpyProvider,
    *,
    agent_changelog_root: Path | None = None,
) -> SoraRuntime:
    proxies: dict[str, ReasoningProvider] = {
        provider.name: provider,
        "deterministic": DeterministicProvider(),
    }
    return SoraRuntime(
        config=RuntimeConfig(
            root=tmp_path / "core",
            identity_root=IDENTITY_ROOT,
            task_timeout_seconds=5.0,
            worker_count=1,
            agent_changelog_root=agent_changelog_root,
        ),
        providers=proxies,
        routing_engine=RoutingEngine(registered_providers=set(proxies.keys())),
    )


async def _run(runtime: SoraRuntime, intent: str) -> tuple[str, str]:
    receipt = await runtime.submit_task(intent)
    report = await runtime.wait_for_task(receipt.task.task_id)
    assert report.status.value == "completed", report
    assert receipt.run is not None
    return receipt.task.task_id, receipt.run.run_id


@pytest.mark.asyncio
async def test_second_task_resumes_the_projects_session(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        _, first_run = await _run(runtime, "Research database lock concurrency")
        assert provider.resumed == []
        run = await runtime.runtime_repository.get_run(first_run)
        assert run is not None and run.native_session_id == f"session-{first_run}"

        second_task, second_run = await _run(runtime, "Research database lock concurrency")
        assert provider.resumed == [f"session-{first_run}"]
        phases = [t.phase for t in await runtime.runtime_repository.traces(second_task)]
        assert "session.resumed" in phases and "session.resume_failed" not in phases
        second = await runtime.runtime_repository.get_run(second_run)
        assert second is not None and second.native_session_id == f"session-{second_run}"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_resume_is_reported_and_falls_back_to_fresh(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity", resume_fails=True)
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        _, first_run = await _run(runtime, "Research database lock concurrency")
        second_task, second_run = await _run(runtime, "Research database lock concurrency")
        assert provider.resumed == [f"session-{first_run}"]
        assert provider.started == [first_run, second_run]  # fresh session still launched
        phases = [t.phase for t in await runtime.runtime_repository.traces(second_task)]
        assert "session.resume_failed" in phases
    finally:
        await runtime.close()


async def _phases(runtime: SoraRuntime, task_id: str) -> list[str]:
    return [trace.phase for trace in await runtime.runtime_repository.traces(task_id)]


@pytest.mark.asyncio
async def test_agent_written_entry_is_verified_against_its_working_root(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    provider = SpyProvider(
        "antigravity", cwd=work, entry_body="## Changed\n\n- the parser, and why\n",
    )
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        task_id, _ = await _run(runtime, "Research database lock concurrency")
        assert "changelog.verified" in await _phases(runtime, task_id)
        entry = work / ENTRY_NAME
        assert entry.is_file() and "the parser" in entry.read_text(encoding="utf-8")
        # Core authored nothing of its own.
        assert not (tmp_path / "core" / "changelog").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_claimed_entry_that_does_not_exist_is_reported_missing(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    provider = SpyProvider("antigravity", cwd=work, reported_path="changelog/never-written.md")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        task_id, _ = await _run(runtime, "Research database lock concurrency")
        phases = await _phases(runtime, task_id)
        assert "changelog.missing" in phases and "changelog.verified" not in phases
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_entry_outside_the_working_directory_is_refused(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside"
    (outside / "changelog").mkdir(parents=True)
    (outside / "changelog" / "escaped.md").write_text("pretend entry", encoding="utf-8")
    provider = SpyProvider(
        "antigravity", cwd=work, reported_path="../outside/changelog/escaped.md",
    )
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        task_id, _ = await _run(runtime, "Research database lock concurrency")
        phases = await _phases(runtime, task_id)
        assert "changelog.missing" in phases and "changelog.verified" not in phases
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_no_entry_at_all_is_reported_rather_than_invented(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        task_id, _ = await _run(runtime, "Research database lock concurrency")
        assert "changelog.missing" in await _phases(runtime, task_id)
        assert not (tmp_path / "core" / "changelog").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_read_only_agent_entry_text_is_stored_verbatim(tmp_path: Path) -> None:
    agent_words = "## Changed\n\n- nothing on disk; sandbox was read-only\n"
    provider = SpyProvider("antigravity", entry_text=agent_words)
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        task_id, _ = await _run(runtime, "Research database lock concurrency")
        assert "changelog.stored" in await _phases(runtime, task_id)
        entry = next((tmp_path / "core" / "changelog" / "agents").glob("*.md"))
        body = entry.read_text(encoding="utf-8")
        assert agent_words.strip() in body
        assert "stored here verbatim by Core" in body  # provenance, not authorship
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_agent_changelog_root_can_be_pointed_at_a_project(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    provider = SpyProvider("antigravity", entry_text="## Changed\n\n- one line\n")
    runtime = make_runtime(tmp_path, provider, agent_changelog_root=project / "changelog")
    await runtime.start()
    try:
        await _run(runtime, "Research database lock concurrency")
        assert list((project / "changelog").glob("*.md"))
        assert not (tmp_path / "core" / "changelog").exists()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_blank_native_session_id_is_not_recorded(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity", session_id_override="")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        _, run_id = await _run(runtime, "Research database lock concurrency")
        run = await runtime.runtime_repository.get_run(run_id)
        assert run is not None and run.native_session_id is None
        assert (
            await runtime.runtime_repository.latest_active_session(
                provider="antigravity", project_id="project-sora",
            )
            is None
        )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_runtime_failure_reports_the_underlying_message(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity", result_error="probe-detail-7")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Research database lock concurrency")
        report = await runtime.wait_for_task(receipt.task.task_id)
        assert report.status.value == "failed", report
        result = await runtime.runtime_repository.result_for_task(receipt.task.task_id)
        assert result is not None
        assert "Runtime failure: ValueError" in result.summary
        assert "probe-detail-7" in result.summary
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_latest_active_session_ignores_other_projects(tmp_path: Path) -> None:
    provider = SpyProvider("antigravity")
    runtime = make_runtime(tmp_path, provider)
    await runtime.start()
    try:
        await _run(runtime, "Research database lock concurrency")
        session = await runtime.runtime_repository.latest_active_session(
            provider="antigravity", project_id="project-sora",
        )
        assert session is not None and session.resume_supported
        assert await runtime.runtime_repository.latest_active_session(
            provider="antigravity", project_id="project-other",
        ) is None
        assert await runtime.runtime_repository.latest_active_session(
            provider="hermes-acp", project_id="project-sora",
        ) is None
    finally:
        await runtime.close()
