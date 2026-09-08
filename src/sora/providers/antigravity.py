"""Antigravity reasoning-provider adapter wrapping the agy CLI."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from sora.providers.base import MalformedProviderResult, ProviderLaunchError

log = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(slots=True)
class _Run:
    process: asyncio.subprocess.Process
    request: ProviderRequest
    task: asyncio.Task[NormalizedResult] | None = None
    session_id: str | None = None
    cancelled: bool = False
    output_text: str = ""
    resume_session_id: str | None = None


def _json_object(text: str) -> dict[str, Any] | None:
    match = _JSON_FENCE.search(text)
    candidate = match.group(1) if match else None
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            candidate = text[start : end + 1]
    if not candidate or not candidate.strip():
        return None
    try:
        val = json.loads(candidate)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        return None


def _strings(data: dict[str, Any], field_name: str) -> tuple[str, ...]:
    val = data.get(field_name)
    if val is None:
        return ()
    if not isinstance(val, list) or any(
        not isinstance(item, str) or not item.strip() for item in val
    ):
        raise MalformedProviderResult(f"invalid Antigravity field: {field_name}")
    return tuple(val)


def parse_antigravity_result(text: str, request: ProviderRequest) -> NormalizedResult:
    """Convert Antigravity CLI output into SORA's NormalizedResult contract."""
    # First check if the top-level output is the agy JSON wrapper
    parsed_json = _json_object(text)
    raw_response = text
    usage_dict: dict[str, Any] | None = None

    if parsed_json and "response" in parsed_json:
        # Wrapped agy format: {"conversation_id": "...", "status": "SUCCESS", "response": "..."}
        raw_response = str(parsed_json.get("response") or "")
        if isinstance(parsed_json.get("usage"), dict):
            usage_dict = parsed_json["usage"]

    # Now inspect raw_response to see if it embeds structured SORA fields
    inner_json = _json_object(raw_response)
    if inner_json and "conclusion" in inner_json:
        data = inner_json
        conclusion = str(data["conclusion"])
        facts = _strings(data, "facts")
        memories = _strings(data, "memory_updates")
        actions_taken = _strings(data, "actions_taken")
        files_read = _strings(data, "files_read")
        files_changed = _strings(data, "files_changed")
        commands_run = _strings(data, "commands_run")
        uncertainties = _strings(data, "uncertainties")
        warnings = _strings(data, "warnings")
        suggested_response = (
            str(data["suggested_response"])
            if isinstance(data.get("suggested_response"), str)
            else None
        )
    else:
        # Plain-text response from Antigravity
        conclusion = raw_response.strip()
        if not conclusion:
            raise MalformedProviderResult("empty Antigravity response")
        facts = ()
        memories = ()
        actions_taken = ()
        files_read = ()
        files_changed = ()
        commands_run = ()
        uncertainties = ()
        warnings = ()
        suggested_response = None

    operations: list[ProposeFactOperation | ProposeMemoryOperation] = []
    for index, content in enumerate(facts):
        operations.append(
            ProposeFactOperation(
                operation="propose_fact",
                operation_id=f"ag-fact-{request.run_id}-{index}",
                fact=ProposedFact(content=content, epistemic_status="inference", confidence=0.5),
            )
        )
    for index, content in enumerate(memories):
        operations.append(
            ProposeMemoryOperation(
                operation="propose_memory",
                operation_id=f"ag-memory-{request.run_id}-{index}",
                memory=ProposedMemory(
                    content=content,
                    scope=request.project_id or request.owner_id,
                ),
            )
        )

    patch = (
        PatchEnvelope(
            patch_id=f"ag-patch-{request.run_id}",
            source_run_id=request.run_id,
            base_revision=0,
            scope=(
                request.owner_id
                if request.project_id is None
                else f"{request.owner_id}/{request.project_id}"
            ),
            provenance="Antigravity normalized result",
            idempotency_key=f"ag-patch-once-{request.run_id}",
            operations=tuple(operations),
        )
        if operations
        else None
    )

    summary_text = conclusion[:200] if len(conclusion) > 200 else conclusion
    return NormalizedResult(
        result_id=f"ag-result-{request.run_id}",
        task_id=request.task_id,
        run_id=request.run_id,
        base_revision=0,
        outcome=ProviderOutcome.COMPLETED,
        summary=summary_text,
        conclusion=conclusion,
        facts=facts,
        actions_taken=actions_taken,
        files_read=files_read,
        files_changed=files_changed,
        commands_run=commands_run,
        uncertainties=uncertainties,
        warnings=warnings,
        memory_updates=memories,
        task_updates=(),
        suggested_response=suggested_response,
        patch=patch,
        usage=usage_dict,
    )


class AntigravityProvider:
    """Antigravity CLI reasoning provider adapter.
    
    Executes reasoning tasks via the local agy CLI in non-interactive print mode,
    capturing native conversation IDs and normalizing output into SORA contracts.
    In accordance with P06 scope, active in-place coding writes remain disabled
    until worktree isolation (P05.3) is completed.
    """

    def __init__(
        self,
        command: str = "agy",
        *,
        args: tuple[str, ...] = (),
        cwd: str | None = None,
        model: str | None = None,
        effort: str = "medium",
        timeout_seconds: float = 600.0,
        max_output_chars: int = 65_536,
    ) -> None:
        if cwd is not None:
            resolved_cwd = Path(cwd).resolve()
            if not resolved_cwd.is_dir():
                raise ValueError("Antigravity working directory must exist")
            self.cwd = str(resolved_cwd)
        else:
            self.cwd = os.getcwd()

        if max_output_chars < 1:
            raise ValueError("max_output_chars must be positive")

        self.command = command
        self.args = args
        self.model = model
        self.effort = effort
        self.timeout_seconds = timeout_seconds
        self.max_output_chars = max_output_chars
        self._runs: dict[str, _Run] = {}
        self._session_ids: dict[str, str] = {}

    async def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider="antigravity",
            sessions=True,
            resume=True,
            events=False,
            steer=False,
            cancel=True,
            tool_restrictions=False,
            display_name="Antigravity",
        )

    async def start(self, request: ProviderRequest) -> str:
        return await self._launch(request)

    async def resume(self, session_id: str, request: ProviderRequest) -> str:
        if not session_id.strip():
            raise ProviderLaunchError(
                ProviderErrorCode.INVALID_REQUEST,
                "Antigravity resume requires a native conversation ID",
            )
        return await self._launch(request, resume_session_id=session_id)

    async def _launch(
        self,
        request: ProviderRequest,
        *,
        resume_session_id: str | None = None,
    ) -> str:
        if request.run_id in self._runs:
            return request.run_id

        executable = shutil.which(self.command) or self.command
        cmd_args = [executable, *self.args, "--output-format", "json", "--effort", self.effort]
        if self.model:
            cmd_args.extend(["--model", self.model])
        if resume_session_id:
            cmd_args.extend(["--conversation", resume_session_id, "--continue"])

        # Format prompt with context and intent
        prompt_text = (
            f"{request.context}\n\n[TASK_INTENT]\n{request.intent}\n\n"
            "Return a clear, reasoned answer. If proposing facts or memory updates, "
            "provide a JSON block with 'conclusion', 'facts', and 'memory_updates'."
        )
        cmd_args.append(f"--print={prompt_text}")

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
        except (FileNotFoundError, OSError) as exc:
            raise ProviderLaunchError(
                ProviderErrorCode.UNAVAILABLE,
                f"Antigravity CLI could not be started: {self.command}",
            ) from exc

        state = _Run(process=process, request=request, resume_session_id=resume_session_id)
        state.task = asyncio.create_task(
            self._execute(state),
            name=f"antigravity-run-{request.run_id}",
        )
        self._runs[request.run_id] = state
        return request.run_id

    async def result(self, run_id: str) -> NormalizedResult:
        state = self._runs.get(run_id)
        if state is None or state.task is None:
            raise ProviderLaunchError(
                ProviderErrorCode.LOST_SESSION,
                f"Antigravity run {run_id} is unknown",
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
                if state.process.returncode is None:
                    try:
                        state.process.kill()
                    except ProcessLookupError:
                        pass
                try:
                    await state.task
                except (asyncio.CancelledError, Exception):
                    pass
            except (asyncio.CancelledError, Exception):
                pass

    async def steer(self, run_id: str, instruction: str) -> None:
        del run_id, instruction
        raise NotImplementedError("steering is unsupported by Antigravity in print mode")

    async def session_id(self, run_id: str) -> str | None:
        state = self._runs.get(run_id)
        return state.session_id if state is not None else self._session_ids.get(run_id)

    async def events(self, run_id: str) -> AsyncIterator[EventEnvelope]:
        del run_id
        if False:
            yield EventEnvelope.model_construct()

    async def _execute(self, state: _Run) -> NormalizedResult:
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                state.process.communicate(),
                timeout=self.timeout_seconds,
            )
        except TimeoutError as exc:
            try:
                state.process.kill()
            except ProcessLookupError:
                pass
            await state.process.communicate()
            raise ProviderLaunchError(
                ProviderErrorCode.TIMED_OUT,
                f"Antigravity CLI timed out after {self.timeout_seconds}s",
            ) from exc
        except asyncio.CancelledError as cancel_exc:
            state.cancelled = True
            try:
                state.process.kill()
            except ProcessLookupError:
                pass
            await state.process.communicate()
            raise ProviderLaunchError(
                ProviderErrorCode.CANCELLED,
                "Antigravity run was cancelled",
            ) from cancel_exc

        if state.cancelled:
            raise ProviderLaunchError(
                ProviderErrorCode.CANCELLED,
                "Antigravity run was cancelled",
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        if len(stdout_text) > self.max_output_chars:
            stdout_text = stdout_text[: self.max_output_chars]

        if state.process.returncode != 0 and not stdout_text.strip():
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
            msg = (
                f"Antigravity CLI failed with code {state.process.returncode}: "
                f"{stderr_text.strip()}"
            )
            raise ProviderLaunchError(
                ProviderErrorCode.INTERNAL,
                msg,
            )

        # Parse wrapper JSON to capture conversation_id if present
        parsed = _json_object(stdout_text)
        if parsed and "conversation_id" in parsed:
            state.session_id = str(parsed["conversation_id"])
            self._session_ids[state.request.run_id] = state.session_id

        return parse_antigravity_result(stdout_text, state.request)
