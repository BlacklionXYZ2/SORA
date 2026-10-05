"""Claude reasoning-provider adapter wrapping headless Claude Code (``claude -p``).

Claude runs on the owner's Claude subscription through the installed CLI; SORA never handles an
API key for it. Each run is one non-interactive ``claude -p --output-format json`` process whose
prompt arrives on standard input, so no command-line length or Windows quoting limit applies.
Native session IDs are captured so a later run can ``--resume`` the conversation.

The adapter adds no permission flags of its own. In print mode Claude Code denies any tool that
would need an interactive approval, so by default it can read and reason but not change files.
The owner opts into more through extra arguments (for example ``--permission-mode acceptEdits``),
exactly as for Antigravity. Like Antigravity, it does not bind writes to an owned worktree.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sora.contracts.changelog import CHANGELOG_INSTRUCTION
from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    PatchEnvelope,
    ProposedFact,
    ProposedMemory,
    ProposeFactOperation,
    ProposeMemoryOperation,
    ProviderCapabilities,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderRequest,
)
from sora.providers.base import MalformedProviderResult, ProviderLaunchError, optional_text

PROVIDER_ID = "claude-code"
_LIST_FIELDS = (
    "facts", "memory_updates", "actions_taken", "files_read", "files_changed", "commands_run",
    "uncertainties", "warnings",
)
_PROMPT_SUFFIX = (
    "\n\nReturn a clear, reasoned answer. If you can, end with one JSON object containing "
    "'conclusion' and any of 'facts', 'memory_updates', 'files_read', 'files_changed', "
    "'commands_run', 'uncertainties', 'changelog_path' and 'changelog_entry'. "
)


@dataclass(slots=True)
class _Run:
    process: asyncio.subprocess.Process
    request: ProviderRequest
    prompt: bytes
    task: asyncio.Task[NormalizedResult] | None = None
    session_id: str | None = None
    cancelled: bool = False


def _last_json_object(text: str) -> dict[str, Any] | None:
    """The last top-level JSON object in ``text``, if any (fenced or bare)."""
    decoder = json.JSONDecoder()
    found: dict[str, Any] | None = None
    index = text.find("{")
    while index != -1:
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if isinstance(value, dict):
            found = value
        index = text.find("{", end)
    return found


def _strings(data: dict[str, Any], field_name: str) -> tuple[str, ...]:
    value = data.get(field_name)
    if value is None:
        return ()
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise MalformedProviderResult(f"invalid Claude field: {field_name}")
    return tuple(value)


def parse_claude_result(stdout: str, request: ProviderRequest) -> NormalizedResult:
    """Convert ``claude -p --output-format json`` output into SORA's NormalizedResult."""
    try:
        wrapper = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise MalformedProviderResult(stdout[:2000]) from exc
    if not isinstance(wrapper, dict) or wrapper.get("type") != "result":
        raise MalformedProviderResult(stdout[:2000])
    text = wrapper.get("result")
    if not isinstance(text, str) or not text.strip():
        raise MalformedProviderResult("empty Claude response")
    usage = wrapper.get("usage") if isinstance(wrapper.get("usage"), dict) else None

    inner = _last_json_object(text)
    structured = inner is not None and isinstance(inner.get("conclusion"), str)
    data: dict[str, Any] = inner if structured and inner is not None else {}
    conclusion = str(data["conclusion"]).strip() if structured else text.strip()
    if not conclusion:
        raise MalformedProviderResult("empty Claude conclusion")
    fields = {name: _strings(data, name) for name in _LIST_FIELDS}

    operations: list[ProposeFactOperation | ProposeMemoryOperation] = []
    for index, content in enumerate(fields["facts"]):
        operations.append(ProposeFactOperation(
            operation="propose_fact",
            operation_id=f"claude-fact-{request.run_id}-{index}",
            fact=ProposedFact(content=content, epistemic_status="inference", confidence=0.5),
        ))
    for index, content in enumerate(fields["memory_updates"]):
        operations.append(ProposeMemoryOperation(
            operation="propose_memory",
            operation_id=f"claude-memory-{request.run_id}-{index}",
            memory=ProposedMemory(content=content, scope=request.project_id or request.owner_id),
        ))
    patch = PatchEnvelope(
        patch_id=f"claude-patch-{request.run_id}",
        source_run_id=request.run_id,
        base_revision=0,
        scope=(request.owner_id if request.project_id is None
               else f"{request.owner_id}/{request.project_id}"),
        provenance="Claude Code normalized result",
        idempotency_key=f"claude-patch-once-{request.run_id}",
        operations=tuple(operations),
    ) if operations else None

    return NormalizedResult(
        result_id=f"claude-result-{request.run_id}",
        task_id=request.task_id,
        run_id=request.run_id,
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary=conclusion[:200],
        conclusion=conclusion,
        facts=fields["facts"],
        actions_taken=fields["actions_taken"],
        files_read=fields["files_read"],
        files_changed=fields["files_changed"],
        commands_run=fields["commands_run"],
        uncertainties=fields["uncertainties"],
        warnings=fields["warnings"],
        memory_updates=fields["memory_updates"],
        task_updates=(),
        suggested_response=(data["suggested_response"]
                            if isinstance(data.get("suggested_response"), str) else None),
        changelog_path=optional_text(data, "changelog_path"),
        changelog_entry=optional_text(data, "changelog_entry"),
        patch=patch,
        usage=usage,
    )


class ClaudeCodeProvider:
    """Headless Claude Code reasoning provider (Claude, in VISION.md's colleague list)."""

    def __init__(
        self,
        command: str = "claude",
        *,
        args: tuple[str, ...] = (),
        cwd: str | None = None,
        model: str | None = None,
        timeout_seconds: float = 600.0,
        max_output_chars: int = 262_144,
    ) -> None:
        if cwd is not None:
            resolved = Path(cwd).resolve()
            if not resolved.is_dir():
                raise ValueError("Claude working directory must exist")
            self.cwd = str(resolved)
        else:
            self.cwd = os.getcwd()
        if max_output_chars < 1:
            raise ValueError("max_output_chars must be positive")
        self.command = command
        self.args = args
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self._runs: dict[str, _Run] = {}
        self._session_ids: dict[str, str] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=PROVIDER_ID,
            sessions=True,
            resume=True,
            events=False,
            steer=False,
            cancel=True,
            tool_restrictions=False,
            filesystem=True,
            worktree_support=False,
            display_name="Claude Code",
        )

    async def start(self, request: ProviderRequest) -> str:
        return await self._launch(request)

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        if not session_id.strip():
            raise ProviderLaunchError(
                ProviderErrorCode.INVALID_REQUEST, "Claude resume requires a native session ID",
            )
        return await self._launch(request, resume_session_id=session_id.strip())

    def command_line(self, request: ProviderRequest, *, resume_session_id: str | None = None,
                     ) -> list[str]:
        if request.reasoning_effort is not None:
            raise ProviderLaunchError(
                ProviderErrorCode.UNSUPPORTED,
                "Claude per-run reasoning effort is not mapped; use its configured default",
            )
        executable = shutil.which(self.command) or self.command
        line = [executable, *self.args, "-p", "--output-format", "json"]
        model = request.model or self.model
        if model:
            line.extend(["--model", model])
        if resume_session_id:
            line.extend(["--resume", resume_session_id])
        return line

    async def _launch(self, request: ProviderRequest, *, resume_session_id: str | None = None,
                      ) -> str:
        if request.run_id in self._runs:
            return request.run_id
        line = self.command_line(request, resume_session_id=resume_session_id)
        prompt = (f"{request.context}\n\n[TASK_INTENT]\n{request.intent}{_PROMPT_SUFFIX}"
                  f"{CHANGELOG_INSTRUCTION}")
        try:
            process = await asyncio.create_subprocess_exec(
                *line,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
        except OSError as exc:
            raise ProviderLaunchError(
                ProviderErrorCode.UNAVAILABLE, f"Claude Code could not be started: {self.command}",
            ) from exc
        state = _Run(process=process, request=request, prompt=prompt.encode("utf-8"))
        state.task = asyncio.create_task(self._execute(state), name=f"claude-run-{request.run_id}")
        self._runs[request.run_id] = state
        return request.run_id

    async def _execute(self, state: _Run) -> NormalizedResult:
        try:
            stdout, stderr = await asyncio.wait_for(
                state.process.communicate(state.prompt), timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            await self._kill(state)
            raise ProviderLaunchError(
                ProviderErrorCode.TIMED_OUT, f"Claude Code timed out after {self.timeout_seconds}s",
            ) from exc
        except asyncio.CancelledError as exc:
            state.cancelled = True
            await self._kill(state)
            raise ProviderLaunchError(
                ProviderErrorCode.CANCELLED, "Claude run was cancelled",
            ) from exc
        if state.cancelled:
            raise ProviderLaunchError(ProviderErrorCode.CANCELLED, "Claude run was cancelled")

        text = stdout.decode("utf-8", errors="replace")[: self.max_output_chars]
        try:
            wrapper = json.loads(text)
        except json.JSONDecodeError:
            wrapper = None
        if isinstance(wrapper, dict):
            session = wrapper.get("session_id")
            if isinstance(session, str) and session.strip():
                state.session_id = session.strip()
                self._session_ids[state.request.run_id] = state.session_id
            if wrapper.get("is_error") is True or (
                isinstance(wrapper.get("subtype"), str) and wrapper["subtype"] != "success"
            ):
                detail = wrapper.get("result") or wrapper.get("subtype") or "unknown failure"
                raise ProviderLaunchError(
                    ProviderErrorCode.INTERNAL,
                    "Claude Code error: " + " ".join(str(detail).split())[:400],
                )
        if state.process.returncode != 0 and not isinstance(wrapper, dict):
            detail = stderr.decode("utf-8", errors="replace").strip()[:400]
            raise ProviderLaunchError(
                ProviderErrorCode.INTERNAL,
                f"Claude Code failed with code {state.process.returncode}: {detail}",
            )
        return parse_claude_result(text, state.request)

    @staticmethod
    async def _kill(state: _Run) -> None:
        if state.process.returncode is None:
            try:
                state.process.kill()
            except ProcessLookupError:
                pass
        await state.process.wait()

    async def result(self, run_id: str) -> NormalizedResult:
        state = self._runs.get(run_id)
        if state is None or state.task is None:
            raise ProviderLaunchError(
                ProviderErrorCode.LOST_SESSION, f"Claude run {run_id} is unknown",
            )
        try:
            return await state.task
        finally:
            self._runs.pop(run_id, None)

    async def status(self, run_id: str) -> str:
        state = self._runs.get(run_id)
        if state is None:
            return "unknown"
        if state.cancelled:
            return "cancelled"
        if state.task is not None and state.task.done():
            if state.task.cancelled():
                return "cancelled"
            return "failed" if state.task.exception() is not None else "completed"
        return "running"

    async def cancel(self, run_id: str) -> None:
        state = self._runs.get(run_id)
        if state is None:
            return
        state.cancelled = True
        if state.process.returncode is None:
            try:
                state.process.terminate()
            except ProcessLookupError:
                pass
        if state.task is not None and not state.task.done():
            try:
                async with asyncio.timeout(1.0):
                    await asyncio.shield(state.task)
            except TimeoutError:
                await self._kill(state)
                try:
                    await state.task
                except (asyncio.CancelledError, Exception):
                    pass
            except (asyncio.CancelledError, Exception):
                pass

    async def steer(self, run_id: str, instruction: str) -> None:
        del run_id, instruction
        raise NotImplementedError("steering is unsupported by Claude Code in print mode")

    async def session_id(self, run_id: str) -> str | None:
        state = self._runs.get(run_id)
        return state.session_id if state is not None else self._session_ids.get(run_id)

    async def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        del run_id
        if False:
            yield EventEnvelope.model_construct()
