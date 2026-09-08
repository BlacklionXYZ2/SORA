"""Concurrent message/task runtime backed by deterministic providers."""

from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from sora.context.compiler import ContextItem, ContextSource, compile_context
from sora.contracts.base import StrictModel
from sora.contracts.models import (
    EventEnvelope,
    NormalizedResult,
    PresentationMode,
    ProviderError,
    ProviderErrorCode,
    ProviderOutcome,
    ProviderRequest,
    ResultPresentation,
    RunStatus,
    TaskRecord,
    TaskStatus,
)
from sora.contracts.provider_support import ProviderMethod, unsupported_method
from sora.identity.loader import load_identity
from sora.persistence.database import SQLiteDatabase
from sora.persistence.records import MessageRecord
from sora.persistence.repository import SoraRepository
from sora.providers.base import (
    MalformedProviderResult,
    ProviderLaunchError,
    ReasoningProvider,
    SessionProvider,
)
from sora.providers.codex import CodexAppServerProvider
from sora.providers.dialogue import DeterministicDialogueProvider, DialogueProvider
from sora.routing import RoutingEngine, TaskIntentCategory
from sora.workspaces import GitWorkspaceManager, WorkspaceRecord

from .repository import RuntimeRepository, SubmissionReceipt


class RuntimeConfig(StrictModel):
    root: Path
    identity_root: Path | None = None
    owner_id: str = "owner-local"
    project_id: str = "project-sora"
    conversation_id: str = "conversation-main"
    worker_count: int = Field(default=2, ge=1, le=16)
    queue_capacity: int = Field(default=100, ge=1, le=10_000)
    lease_seconds: float = Field(default=5.0, gt=0)
    task_timeout_seconds: float = Field(default=30.0, gt=0)
    max_attempts: int = Field(default=3, ge=1, le=10)
    context_max_chars: int = Field(default=8_000, ge=256)
    secrets: tuple[str, ...] = ()
    coding_repository_root: Path | None = None
    coding_workspace_root: Path | None = None
    coding_base_ref: str | None = None

    @model_validator(mode="after")
    def validate_coding_workspace(self) -> RuntimeConfig:
        configured = (
            self.coding_repository_root,
            self.coding_workspace_root,
            self.coding_base_ref,
        )
        if any(value is not None for value in configured) and not all(
            value is not None for value in configured
        ):
            raise ValueError(
                "coding_repository_root, coding_workspace_root, and coding_base_ref "
                "must be configured together"
            )
        if self.coding_repository_root is not None and not self.coding_repository_root.is_dir():
            raise ValueError("coding_repository_root must be an existing directory")
        if self.coding_base_ref is not None and not self.coding_base_ref.strip():
            raise ValueError("coding_base_ref cannot be blank")
        return self


class TaskReport(StrictModel):
    task_id: str
    status: TaskStatus
    message: str
    completed: bool
    result: NormalizedResult | None = None


class SoraRuntime:
    def __init__(
        self,
        config: RuntimeConfig,
        provider: ReasoningProvider | None = None,
        dialogue_provider: DialogueProvider | None = None,
        *,
        providers: Mapping[str, ReasoningProvider] | None = None,
        routing_engine: RoutingEngine | None = None,
    ):
        self.config = config
        self.providers: dict[str, ReasoningProvider] = dict(providers) if providers else {}
        if provider is not None:
            self.provider = provider
            if "default" not in self.providers:
                self.providers["default"] = provider
            if "deterministic" not in self.providers:
                self.providers["deterministic"] = provider
        elif self.providers:
            self.provider = next(iter(self.providers.values()))
        else:
            raise ValueError("SoraRuntime requires at least one provider")

        self.dialogue_provider = dialogue_provider or DeterministicDialogueProvider()
        self.workspace_manager = (
            GitWorkspaceManager(config.coding_workspace_root)
            if config.coding_workspace_root is not None
            else None
        )
        self.routing_engine = routing_engine or RoutingEngine(
            registered_providers=set(self.providers.keys()),
            has_worktree_isolation=self.workspace_manager is not None,
        )
        self.routing_engine.has_worktree_isolation = self.workspace_manager is not None
        database = SQLiteDatabase(config.root / "data" / "sora.db")

        self.repository = SoraRepository(database)
        self.runtime_repository = RuntimeRepository(self.repository)
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=config.queue_capacity)
        self._workers: list[asyncio.Task[None]] = []
        self._started = False

    def _get_provider(self, name: str) -> ReasoningProvider:
        if name in self.providers:
            return self.providers[name]
        if "default" in self.providers:
            return self.providers["default"]
        return self.provider

    async def start(self) -> list[str]:
        if self._started:
            return []
        await self.repository.database.initialize()
        await self.repository.register_owner(self.config.owner_id)
        await self.repository.register_project(self.config.project_id, self.config.owner_id)
        await self.repository.register_conversation(
            self.config.conversation_id, self.config.owner_id, self.config.project_id
        )
        if await self.repository.active_identity(self.config.owner_id) is None:
            bundle = load_identity(self.config.identity_root or self.config.root / "identity")
            await self.repository.activate_identity(
                self.config.owner_id, bundle, source="runtime bootstrap"
            )

        for _p_name, p_inst in list(self.providers.items()):
            try:
                caps = await p_inst.capabilities()
                self.providers[caps.provider] = p_inst
                self.routing_engine.registered_providers.add(caps.provider)
            except Exception:
                pass

        # The initial runtime is single-process. Any lease found during process startup belongs to
        # a prior process and is therefore orphaned even if its wall-clock expiry is still future.
        reconciled = await self.runtime_repository.reconcile_expired(
            datetime.now(UTC), include_unexpired=True
        )
        self._workers = [
            asyncio.create_task(self._worker(index), name=f"sora-worker-{index}")
            for index in range(self.config.worker_count)
        ]
        for run_id in await self.runtime_repository.pending_run_ids():
            await self._queue.put(run_id)
        self._started = True
        return reconciled

    async def close(self, *, drain: bool = True) -> None:
        if not self._started:
            return
        if drain:
            await self._queue.join()
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False

    async def submit_task(
        self,
        intent: str,
        *,
        idempotency_key: str | None = None,
        explicit_provider: str | None = None,
        context_scope: str | None = None,
        is_local_only: bool = False,
    ) -> SubmissionReceipt:
        self._require_started()
        decision = self.routing_engine.route(
            intent,
            explicit_provider=explicit_provider,
            context_scope=context_scope,
            is_local_only=is_local_only,
        )
        if decision.metadata.get("p05_deferred") is True:
            raise ProviderLaunchError(
                ProviderErrorCode.INVALID_REQUEST,
                "Coding write was not submitted because no owned P05 workspace is configured.",
            )
        target_provider_inst = self._get_provider(decision.selected_provider)
        target_caps = await target_provider_inst.capabilities()
        target_provider = target_caps.provider
        receipt = await self.runtime_repository.submit(
            owner_id=self.config.owner_id,
            project_id=self.config.project_id,
            conversation_id=self.config.conversation_id,
            intent=intent,
            idempotency_key=idempotency_key or f"submission-{uuid.uuid4()}",
            now=datetime.now(UTC),
            provider=target_provider,
            requested_backend=explicit_provider or "auto",
            max_active_tasks=self.config.queue_capacity,
        )
        await self.runtime_repository.record_trace(
            correlation_id=receipt.task.task_id,
            phase="routing.selected",
            now=datetime.now(UTC),
            message_id=receipt.message_id,
            task_id=receipt.task.task_id,
            run_id=receipt.run.run_id,
            fields={
                "selected_provider": decision.selected_provider,
                "rule_name": decision.rule_name,
                "reason": decision.reason,
                "category": decision.category.value,
                "fallback_providers": list(decision.fallback_providers),
            },
            secrets=self.config.secrets,
        )
        await self.runtime_repository.record_trace(
            correlation_id=receipt.task.task_id,
            phase="task.submitted" if receipt.created else "task.duplicate",
            now=datetime.now(UTC),
            message_id=receipt.message_id,
            task_id=receipt.task.task_id,
            run_id=receipt.run.run_id,
            fields={"provider": target_provider},
            secrets=self.config.secrets,
        )
        if receipt.created:
            await self._queue.put(receipt.run.run_id)
        return receipt

    def dialogue_status(self) -> str:
        """SORA dialogue availability (independent from delegated background tasks)."""
        return "available"

    async def active_specialists(self) -> tuple[str, ...]:
        """Return list of active specialist harnesses currently reasoning."""
        run_ids = await self.runtime_repository.active_run_ids()
        specialists: set[str] = set()
        for rid in run_ids:
            run = await self.runtime_repository.get_run(rid)
            if run is not None:
                specialists.add(run.provider)
        return tuple(sorted(specialists))

    def present_result(
        self,
        result: NormalizedResult,
        mode: PresentationMode | None = None,
    ) -> ResultPresentation:
        """Create a truthful, proportional ResultPresentation without scratchpads."""
        if mode is None:
            if result.outcome is ProviderOutcome.FAILED:
                mode = PresentationMode.EXPLAIN
            elif result.uncertainties or result.warnings:
                mode = PresentationMode.EXPLAIN
            elif len(result.files_changed) > 5:
                mode = PresentationMode.WALKTHROUGH
            elif len(result.files_changed) > 2 or len(result.commands_run) > 5:
                mode = PresentationMode.EXPLAIN
            elif result.facts or (result.patch and result.patch.operations):
                mode = PresentationMode.EXPLAIN
            else:
                mode = PresentationMode.BRIEF

        significance: Literal["low", "medium", "high"] = "low"
        if len(result.files_changed) > 2 or result.outcome is ProviderOutcome.FAILED:
            significance = "high"
        elif result.files_changed or result.facts or result.uncertainties:
            significance = "medium"

        explanation = result.conclusion
        if result.error:
            explanation = result.error.message

        raw_prov = result.patch.provenance if result.patch else "SORA"
        actor = raw_prov
        lower_prov = raw_prov.lower()
        if "antigravity" in lower_prov:
            actor = "Antigravity"
        elif "hermes" in lower_prov:
            actor = "Hermes"
        elif "codex" in lower_prov or "cody" in lower_prov:
            actor = "Cody"

        return ResultPresentation(
            presentation_id=f"presentation-{result.result_id}",
            result_id=result.result_id,
            mode=mode,
            significance=significance,
            actor_provenance=actor,
            summary=result.summary,
            explanation=explanation,
            evidence_refs=result.patch.evidence_refs if result.patch else (),
            artifact_refs=(),
            attention_target_id=None,
            physical_cues=("nod",) if result.outcome is ProviderOutcome.COMPLETED else (),
            attention_required=(
                result.outcome is ProviderOutcome.FAILED
                or bool(result.uncertainties)
            ),
        )

    async def dialogue(self, text: str) -> str:
        self._require_started()
        now = datetime.now(UTC)
        user = MessageRecord(
            message_id=f"message-{uuid.uuid4()}",
            conversation_id=self.config.conversation_id,
            owner_id=self.config.owner_id,
            project_id=self.config.project_id,
            role="user",
            content=text,
            provenance="user input",
            created_at=now,
        )
        response = await self.dialogue_provider.respond(text, "")
        assistant = MessageRecord(
            message_id=f"message-{uuid.uuid4()}",
            conversation_id=self.config.conversation_id,
            owner_id=self.config.owner_id,
            project_id=self.config.project_id,
            role="assistant",
            content=response,
            provenance="deterministic dialogue",
            created_at=now,
        )
        await self.repository.append_message(user)
        await self.repository.append_message(assistant)
        return response


    async def stream_dialogue(self, text: str) -> AsyncIterator[str]:
        """Stream one deterministic response after atomically finalizing its durable turn."""

        response = await self.dialogue(text)
        words = response.split(" ")
        for index, word in enumerate(words):
            if index:
                yield " "
            yield word
            await asyncio.sleep(0)

    async def wait_for_task(self, task_id: str, *, timeout: float = 30.0) -> TaskReport:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            report = await self.report(task_id)
            if report.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                task = await self.runtime_repository.get_task(task_id)
                if (
                    task is None
                    or task.active_run_id is None
                    or not await self.runtime_repository.has_lease(task.active_run_id)
                ):
                    return report
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError(f"task {task_id} did not finish within {timeout} seconds")
            await asyncio.sleep(0.01)

    async def report(self, task_id: str) -> TaskReport:
        task = await self.runtime_repository.get_task(task_id)
        if task is None:
            raise LookupError(f"task {task_id} does not exist")
        result = await self.runtime_repository.result_for_task(task_id)
        if task.status is TaskStatus.COMPLETED and result is not None:
            message = result.conclusion or result.summary
            return TaskReport(
                task_id=task_id,
                status=task.status,
                message=message,
                completed=True,
                result=result,
            )
        if task.status is TaskStatus.FAILED:
            detail = result.error.code.value if result and result.error else "runtime_failure"
            return TaskReport(
                task_id=task_id,
                status=task.status,
                message=f"The task failed truthfully with {detail}; no completion is claimed.",
                completed=False,
                result=result,
            )
        if task.status is TaskStatus.CANCELLED:
            return TaskReport(
                task_id=task_id,
                status=task.status,
                message="The task was cancelled; any late result is evidence only.",
                completed=False,
                result=result,
            )
        return TaskReport(
            task_id=task_id,
            status=task.status,
            message=f"The task is still {task.status.value}; no completed result is available.",
            completed=False,
            result=result,
        )

    async def cancel(self, task_id: str) -> bool:
        task = await self.runtime_repository.get_task(task_id)
        if task is None or task.active_run_id is None:
            return False
        run = await self.runtime_repository.get_run(task.active_run_id)
        if run is None:
            return False
        changed = await self.runtime_repository.request_cancel(run.run_id, datetime.now(UTC))
        if changed and run.status is not RunStatus.PENDING:
            provider = self._get_provider(run.provider)
            await provider.cancel(run.run_id)
        return changed

    async def retry(self, task_id: str) -> TaskRecord:
        self._require_started()
        run = await self.runtime_repository.retry_task(
            task_id,
            now=datetime.now(UTC),
            max_attempts=self.config.max_attempts,
        )
        await self.runtime_repository.record_trace(
            correlation_id=task_id,
            phase="task.retried",
            now=datetime.now(UTC),
            task_id=task_id,
            run_id=run.run_id,
            fields={"attempt": run.attempt, "max_attempts": self.config.max_attempts},
            secrets=self.config.secrets,
        )
        await self._queue.put(run.run_id)
        task = await self.runtime_repository.get_task(task_id)
        if task is None:
            raise LookupError(f"task {task_id} disappeared after retry")
        return task

    async def steer(self, task_id: str, instruction: str) -> ProviderError | None:
        task = await self.runtime_repository.get_task(task_id)
        if task is None or task.active_run_id is None:
            return ProviderError(
                code=ProviderErrorCode.INVALID_REQUEST,
                message=f"task {task_id} has no active run",
            )
        run = await self.runtime_repository.get_run(task.active_run_id)
        provider = self._get_provider(run.provider if run else "default")
        capabilities = await provider.capabilities()
        error = unsupported_method(capabilities, ProviderMethod.STEER)
        if error is not None:
            return error
        await provider.steer(task.active_run_id, instruction)
        await self.runtime_repository.record_trace(
            correlation_id=task_id,
            phase="task.steered",
            now=datetime.now(UTC),
            task_id=task_id,
            run_id=task.active_run_id,
            fields={"instruction_length": len(instruction)},
            secrets=self.config.secrets,
        )
        return None

    async def steer_from_conversation(self, instruction: str) -> tuple[str | None, str]:
        """Disambiguate conversational steering and steer the targeted active task."""
        tasks = await self.runtime_repository.list_tasks()
        target_task_id = self.routing_engine.disambiguate_steering(instruction, tasks)
        if target_task_id is None:
            return None, "Target task could not be determined or is ambiguous."
        err = await self.steer(target_task_id, instruction)
        if err is not None:
            return target_task_id, f"Could not steer task {target_task_id}: {err.message}"
        return target_task_id, f"Steered task {target_task_id}."

    async def inspect_state(self) -> dict[str, object]:
        return {
            "schema_version": await self.repository.database.schema_version(),
            "revision": await self.repository.revision(),
            "tasks": len(await self.runtime_repository.list_tasks()),
            "leases": await self.runtime_repository.lease_count(),
            "pending_outbox": len(await self.runtime_repository.pending_outbox()),
        }

    async def dispatch_outbox(
        self, consumer: Callable[[EventEnvelope], Awaitable[None]], *, limit: int = 100
    ) -> int:
        delivered = 0
        for record in await self.runtime_repository.pending_outbox(limit):
            event = EventEnvelope.model_validate_json(record.payload)
            await consumer(event)
            await self.runtime_repository.mark_outbox_delivered(record.event_id, datetime.now(UTC))
            delivered += 1
        return delivered

    async def _worker(self, index: int) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await self._execute(run_id, f"worker-{index}")
            finally:
                self._queue.task_done()

    async def _execute(self, run_id: str, lease_owner: str) -> None:
        started_at = time.perf_counter()
        workspace_record: WorkspaceRecord | None = None
        workspace_lease_owner: str | None = None
        workspace_artifact_captured = False
        result: NormalizedResult | None = None
        now = datetime.now(UTC)
        deadline = now + timedelta(seconds=self.config.task_timeout_seconds)
        acquired = await self.runtime_repository.acquire_lease(
            run_id,
            lease_owner=lease_owner,
            now=now,
            expires_at=now
            + timedelta(
                seconds=max(self.config.lease_seconds, self.config.task_timeout_seconds + 1)
            ),
            deadline=deadline,
        )
        if not acquired:
            return
        run = await self.runtime_repository.get_run(run_id)
        if run is None:
            await self.runtime_repository.release_lease(run_id)
            return
        task = await self.runtime_repository.get_task(run.task_id)
        if task is None:
            await self.runtime_repository.release_lease(run_id)
            return
        provider = self._get_provider(run.provider)
        try:
            request = await self._provider_request(task, run_id, deadline)
            provider, request, workspace_record, workspace_lease_owner = (
                await self._bind_coding_workspace(
                    provider,
                    request,
                    task=task,
                    run_id=run_id,
                    worker_lease_owner=lease_owner,
                )
            )
            if workspace_record is not None:
                await self._record_workspace_allocation(task, run_id, workspace_record)
            await self.runtime_repository.record_trace(
                correlation_id=task.task_id,
                phase="provider.launching",
                now=datetime.now(UTC),
                message_id=task.creator_message_id,
                task_id=task.task_id,
                run_id=run_id,
                fields={
                    "context_manifest_ref": request.context_manifest_ref,
                    "provider": run.provider,
                },
                secrets=self.config.secrets,
            )
            try:
                await provider.start(request)
            except ProviderLaunchError as launch_exc:
                if (
                    launch_exc.code is ProviderErrorCode.UNAVAILABLE
                    and task.requested_backend == "auto"
                ):
                    decision = self.routing_engine.route(request.intent)
                    fallbacks = [
                        fb
                        for fb in decision.fallback_providers
                        if fb != run.provider and fb in self.providers
                    ]
                    if fallbacks:
                        fallback_name = fallbacks[0]
                        fallback_provider = self._get_provider(fallback_name)
                        await self.runtime_repository.record_trace(
                            correlation_id=task.task_id,
                            phase="routing.fallback",
                            now=datetime.now(UTC),
                            task_id=task.task_id,
                            run_id=run_id,
                            fields={
                                "original_provider": run.provider,
                                "fallback_provider": fallback_name,
                                "reason": str(launch_exc),
                            },
                            secrets=self.config.secrets,
                        )
                        provider = fallback_provider
                        await self.runtime_repository.set_effective_provider(
                            run_id,
                            fallback_name,
                        )
                        await provider.start(request)
                    else:
                        raise
                else:
                    raise

            await self.runtime_repository.mark_running(run_id, datetime.now(UTC))
            try:
                async with asyncio.timeout(self.config.task_timeout_seconds):
                    result = await provider.result(run_id)
            except TimeoutError:
                await provider.cancel(run_id)
                result = self._failure_result(
                    task.task_id,
                    run_id,
                    ProviderErrorCode.TIMED_OUT,
                    "The reasoning provider exceeded its deadline.",
                )
            except MalformedProviderResult as exc:
                await provider.cancel(run_id)
                result = self._failure_result(
                    task.task_id,
                    run_id,
                    ProviderErrorCode.MALFORMED_RESULT,
                    "The provider returned malformed output.",
                    uncertainty=(
                        "Raw output retained only as a redacted diagnostic "
                        f"({len(exc.raw_output)} bytes)."
                    ),
                )
            await self._attach_native_session(provider, task, run_id, request)
            if workspace_record is not None and workspace_lease_owner is not None:
                artifact_ref = await self._capture_coding_artifact(
                    provider,
                    workspace_record,
                    workspace_lease_owner,
                    task=task,
                    run_id=run_id,
                    result=result,
                )
                result = result.model_copy(
                    update={
                        "task_updates": (
                            *result.task_updates,
                            f"review_artifact:{artifact_ref}",
                        )
                    }
                )
                workspace_artifact_captured = True
            await self._accept_result(task.task_id, run_id, result)
        except ProviderLaunchError as exc:
            result = self._failure_result(
                task.task_id,
                run_id,
                exc.code,
                str(exc),
                uncertainty=(
                    "The external launch may have occurred and must be reconciled."
                    if exc.code is ProviderErrorCode.UNCERTAIN_LAUNCH
                    else None
                ),
            )
            await self.repository.record_result(result, self.config.owner_id)
            await self.runtime_repository.finish(
                run_id,
                run_status=RunStatus.FAILED,
                task_status=TaskStatus.FAILED,
                outcome=(
                    ProviderOutcome.UNKNOWN
                    if exc.code is ProviderErrorCode.UNCERTAIN_LAUNCH
                    else ProviderOutcome.FAILED
                ),
                result_ref=result.result_id,
                now=datetime.now(UTC),
            )
        except Exception as exc:
            result = self._failure_result(
                task.task_id,
                run_id,
                ProviderErrorCode.INTERNAL,
                f"Runtime failure: {type(exc).__name__}",
            )
            await self.repository.record_result(result, self.config.owner_id)
            current_run = await self.runtime_repository.get_run(run_id)
            if current_run and current_run.status in {
                RunStatus.LAUNCHING,
                RunStatus.RUNNING,
                RunStatus.CANCEL_REQUESTED,
            }:
                await self.runtime_repository.finish(
                    run_id,
                    run_status=RunStatus.FAILED,
                    task_status=TaskStatus.FAILED,
                    outcome=ProviderOutcome.FAILED,
                    result_ref=result.result_id,
                    now=datetime.now(UTC),
                )
        finally:
            if workspace_record is not None and workspace_lease_owner is not None:
                if not workspace_artifact_captured:
                    try:
                        await self._capture_coding_artifact(
                            provider,
                            workspace_record,
                            workspace_lease_owner,
                            task=task,
                            run_id=run_id,
                            result=result,
                        )
                    except Exception as artifact_exc:
                        await self.runtime_repository.record_trace(
                            correlation_id=task.task_id,
                            phase="workspace.artifact_failed",
                            now=datetime.now(UTC),
                            message_id=task.creator_message_id,
                            task_id=task.task_id,
                            run_id=run_id,
                            fields={"error": type(artifact_exc).__name__},
                            secrets=self.config.secrets,
                        )
                try:
                    assert self.workspace_manager is not None
                    await asyncio.to_thread(
                        self.workspace_manager.release_lease,
                        workspace_record.workspace_id,
                        lease_owner=workspace_lease_owner,
                    )
                    await self.runtime_repository.record_trace(
                        correlation_id=task.task_id,
                        phase="workspace.lease_released",
                        now=datetime.now(UTC),
                        message_id=task.creator_message_id,
                        task_id=task.task_id,
                        run_id=run_id,
                        fields={"workspace_id": workspace_record.workspace_id},
                        secrets=self.config.secrets,
                    )
                except Exception as lease_exc:
                    await self.runtime_repository.record_trace(
                        correlation_id=task.task_id,
                        phase="workspace.lease_release_failed",
                        now=datetime.now(UTC),
                        message_id=task.creator_message_id,
                        task_id=task.task_id,
                        run_id=run_id,
                        fields={"error": type(lease_exc).__name__},
                        secrets=self.config.secrets,
                    )
            elapsed = (time.perf_counter() - started_at) * 1000
            await self.runtime_repository.record_trace(
                correlation_id=task.task_id,
                phase="run.finished",
                now=datetime.now(UTC),
                message_id=task.creator_message_id,
                task_id=task.task_id,
                run_id=run_id,
                duration_ms=elapsed,
                fields={"lease_owner": lease_owner},
                secrets=self.config.secrets,
            )
            await self.runtime_repository.release_lease(run_id)

    async def _bind_coding_workspace(
        self,
        provider: ReasoningProvider,
        request: ProviderRequest,
        *,
        task: TaskRecord,
        run_id: str,
        worker_lease_owner: str,
    ) -> tuple[ReasoningProvider, ProviderRequest, WorkspaceRecord | None, str | None]:
        category = self.routing_engine.classify_intent(request.intent)
        if category is not TaskIntentCategory.CODING_WRITE:
            return provider, request, None, None
        if not isinstance(provider, CodexAppServerProvider):
            raise ProviderLaunchError(
                ProviderErrorCode.UNSUPPORTED,
                "Coding writes require the managed Codex worktree adapter.",
            )
        if (
            self.workspace_manager is None
            or self.config.coding_repository_root is None
            or self.config.coding_base_ref is None
        ):
            raise ProviderLaunchError(
                ProviderErrorCode.INVALID_REQUEST,
                "Coding write has no configured owned-worktree allocator.",
            )
        workspace_id = f"workspace-{run_id}"
        workspace_lease_owner = f"{worker_lease_owner}.{run_id}"
        record = await asyncio.to_thread(
            self.workspace_manager.allocate,
            self.config.coding_repository_root,
            workspace_id=workspace_id,
            task_id=task.task_id,
            base_ref=self.config.coding_base_ref,
            lease_owner=workspace_lease_owner,
            lease_seconds=max(
                self.config.lease_seconds,
                self.config.task_timeout_seconds + 30,
            ),
        )
        bound_provider = provider.for_owned_workspace(
            record,
            self.workspace_manager,
            lease_owner=workspace_lease_owner,
        )
        bound_request = request.model_copy(
            update={
                "workspace_ref": record.workspace_id,
                "artifact_destination": str(
                    self.workspace_manager.artifact_root / record.workspace_id
                ),
            }
        )
        return bound_provider, bound_request, record, workspace_lease_owner

    async def _record_workspace_allocation(
        self,
        task: TaskRecord,
        run_id: str,
        record: WorkspaceRecord,
    ) -> None:
        await self.runtime_repository.record_trace(
            correlation_id=task.task_id,
            phase="workspace.allocated",
            now=datetime.now(UTC),
            message_id=task.creator_message_id,
            task_id=task.task_id,
            run_id=run_id,
            fields={
                "workspace_id": record.workspace_id,
                "base_ref": record.requested_base_ref,
                "base_commit": record.base_commit,
                "worktree_path": str(record.worktree_path),
                "source_dirty_before": list(record.source_dirty_before),
            },
            secrets=self.config.secrets,
        )

    async def _capture_coding_artifact(
        self,
        provider: ReasoningProvider,
        record: WorkspaceRecord,
        lease_owner: str,
        *,
        task: TaskRecord,
        run_id: str,
        result: NormalizedResult | None,
    ) -> Path:
        assert self.workspace_manager is not None
        capabilities = await provider.capabilities()
        artifact, destination = await asyncio.to_thread(
            self.workspace_manager.capture_run_artifact,
            record.workspace_id,
            lease_owner=lease_owner,
            provider=capabilities.provider,
            result=result,
        )
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        await self.runtime_repository.record_trace(
            correlation_id=task.task_id,
            phase="workspace.artifact_captured",
            now=datetime.now(UTC),
            message_id=task.creator_message_id,
            task_id=task.task_id,
            run_id=run_id,
            fields={
                "workspace_id": record.workspace_id,
                "artifact_ref": str(destination),
                "artifact_sha256": digest,
                "base_commit": artifact.workspace.base_commit,
                "head_commit": artifact.workspace.head_commit,
                "changed_files": list(artifact.workspace.changed_files),
                "verification_commands": list(artifact.verification_commands),
            },
            secrets=self.config.secrets,
        )
        return destination

    async def _attach_native_session(
        self,
        provider: ReasoningProvider,
        task: TaskRecord,
        run_id: str,
        request: ProviderRequest,
    ) -> None:
        if not isinstance(provider, SessionProvider):
            return
        native_session_id = await provider.session_id(run_id)
        if native_session_id is None:
            return
        session = await self.runtime_repository.attach_native_session(
            run_id,
            native_session_id=native_session_id,
            context_fingerprint=hashlib.sha256(request.context.encode("utf-8")).hexdigest(),
            now=datetime.now(UTC),
        )
        await self.runtime_repository.record_trace(
            correlation_id=task.task_id,
            phase="session.attached",
            now=datetime.now(UTC),
            message_id=task.creator_message_id,
            task_id=task.task_id,
            run_id=run_id,
            fields={
                "session_id": session.session_id,
                "provider": session.provider,
            },
            secrets=self.config.secrets,
        )

    async def _accept_result(self, task_id: str, run_id: str, result: NormalizedResult) -> None:
        await self.repository.record_result(result, self.config.owner_id)
        await self.runtime_repository.record_trace(
            correlation_id=task_id,
            phase="result.accepted",
            now=datetime.now(UTC),
            task_id=task_id,
            run_id=run_id,
            fields={"result_id": result.result_id, "outcome": result.outcome.value},
            secrets=self.config.secrets,
        )
        task = await self.runtime_repository.get_task(task_id)
        if task is None:
            raise LookupError(f"task {task_id} disappeared")
        if task.status is TaskStatus.CANCEL_REQUESTED:
            run_status = (
                RunStatus.CANCELLED
                if result.outcome is ProviderOutcome.CANCELLED
                else RunStatus.COMPLETED
            )
            await self.runtime_repository.finish(
                run_id,
                run_status=run_status,
                task_status=TaskStatus.CANCELLED,
                outcome=result.outcome,
                result_ref=result.result_id,
                now=datetime.now(UTC),
            )
            return
        if result.outcome is ProviderOutcome.COMPLETED:
            if result.patch is not None:
                commit = await self.repository.apply_patch(result.patch, self.config.owner_id)
                await self.runtime_repository.record_trace(
                    correlation_id=task_id,
                    phase="patch.applied",
                    now=datetime.now(UTC),
                    task_id=task_id,
                    run_id=run_id,
                    fields={
                        "patch_id": result.patch.patch_id,
                        "disposition": commit.disposition.value,
                        "revision": commit.revision,
                    },
                    secrets=self.config.secrets,
                )
            await self.runtime_repository.finish(
                run_id,
                run_status=RunStatus.COMPLETED,
                task_status=TaskStatus.COMPLETED,
                outcome=result.outcome,
                result_ref=result.result_id,
                now=datetime.now(UTC),
            )
            return
        if result.outcome is ProviderOutcome.CANCELLED:
            await self.runtime_repository.finish(
                run_id,
                run_status=RunStatus.CANCELLED,
                task_status=TaskStatus.CANCELLED,
                outcome=result.outcome,
                result_ref=result.result_id,
                now=datetime.now(UTC),
            )
            return
        await self.runtime_repository.finish(
            run_id,
            run_status=RunStatus.FAILED,
            task_status=TaskStatus.FAILED,
            outcome=result.outcome,
            result_ref=result.result_id,
            now=datetime.now(UTC),
        )

    async def _provider_request(
        self, task: TaskRecord, run_id: str, deadline: datetime
    ) -> ProviderRequest:
        identity = await self.repository.active_identity(self.config.owner_id)
        if identity is None:
            raise RuntimeError("active identity is unavailable")
        messages = await self.repository.list_messages(self.config.conversation_id)
        context_items = tuple(
            ContextItem(
                source_id=message.message_id,
                source=(
                    ContextSource.USER_MESSAGE
                    if message.role == "user"
                    else ContextSource.SORA_MESSAGE
                ),
                owner_id=message.owner_id,
                project_id=message.project_id,
                content=message.content,
                sensitivity=message.sensitivity,
            )
            for message in messages[-20:]
        )
        from sora.identity.loader import IdentityBundle

        compiled = compile_context(
            identity=IdentityBundle(
                content_hash=identity.content_hash,
                files=identity.files,
            ),
            owner_id=self.config.owner_id,
            project_id=self.config.project_id,
            constraints=task.constraints,
            items=context_items,
            observed_at=datetime.now(UTC),
            max_chars=self.config.context_max_chars,
        )
        manifest_ref = f"context-{task.task_id}-{task.base_revision}"
        await self.runtime_repository.record_trace(
            correlation_id=task.task_id,
            phase="context.compiled",
            now=datetime.now(UTC),
            message_id=task.creator_message_id,
            task_id=task.task_id,
            run_id=run_id,
            fields={
                "manifest_ref": manifest_ref,
                "rendered_chars": compiled.manifest.rendered_chars,
                "sources": [
                    {
                        "source_id": entry.source_id,
                        "included": entry.included,
                        "reason": entry.reason,
                    }
                    for entry in compiled.manifest.entries
                ],
            },
            secrets=self.config.secrets,
        )
        return ProviderRequest(
            request_id=f"request-{run_id}",
            task_id=task.task_id,
            run_id=run_id,
            owner_id=self.config.owner_id,
            project_id=self.config.project_id,
            intent=next(
                message.content
                for message in messages
                if message.message_id == task.creator_message_id
            ),
            context=compiled.text,
            context_manifest_ref=manifest_ref,
            deadline=deadline,
            token_budget=4_000,
            artifact_destination=str(self.config.root / ".local" / "artifacts" / run_id),
            idempotency_key=f"provider-start-{run_id}",
        )

    @staticmethod
    def _failure_result(
        task_id: str,
        run_id: str,
        code: ProviderErrorCode,
        message: str,
        *,
        uncertainty: str | None = None,
    ) -> NormalizedResult:
        return NormalizedResult(
            result_id=f"result-{run_id}",
            task_id=task_id,
            run_id=run_id,
            base_revision=0,
            outcome=ProviderOutcome.FAILED,
            summary=message,
            uncertainties=(uncertainty,) if uncertainty else (),
            error=ProviderError(code=code, message=message),
        )

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("SORA runtime has not been started")
