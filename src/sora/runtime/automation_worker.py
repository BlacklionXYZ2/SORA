"""One bounded Core-owned scheduler, using the existing task queue and admission pipeline."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sora.contracts.automation import AutomationOccurrence
from sora.contracts.automation_api import SchedulerState
from sora.contracts.base import require_aware
from sora.providers.base import ProviderLaunchError
from sora.runtime.automation_admission import AutomationAdmission
from sora.runtime.automation_store import (
    AutomationConflict,
    AutomationStorageError,
    AutomationStore,
)
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError

if TYPE_CHECKING:
    from sora.runtime.repository import SubmissionReceipt
    from sora.runtime.service import SoraRuntime


class AutomationWorker:
    def __init__(
        self,
        runtime: SoraRuntime,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        interval: float = 1.0,
        batch_size: int = 32,
    ):
        if not 0.05 <= interval <= 60 or not 1 <= batch_size <= 64:
            raise ValueError("Invalid bounded scheduler configuration")
        self.runtime, self.clock, self.interval, self.batch_size = (
            runtime,
            clock,
            interval,
            batch_size,
        )
        self.store = AutomationStore(
            runtime.repository,
            runtime.config.owner_id,
            runtime.config.project_id,
            str(uuid.uuid4()),
        )
        self.admission = AutomationAdmission(self.store)
        self.started_at: datetime | None = None
        self.closing = False
        self.degraded = False
        self.task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._tick_lock = asyncio.Lock()
        self._definition_after = 0
        self._occurrence_after = 0

    @property
    def state(self) -> SchedulerState:
        if self.task is None:
            return "stopped" if self.closing else "unavailable"
        if self.task.done():
            return "stopped" if self.closing else "degraded"
        if self.closing:
            return "stopping"
        return "degraded" if self.degraded else "running"

    def start(self) -> None:
        if self.task is not None and not self.task.done():
            return
        self.started_at = require_aware(self.clock(), "clock").astimezone(UTC)
        self.closing = False
        self.degraded = False
        self._stop.clear()
        self._definition_after = self._occurrence_after = 0
        self.task = asyncio.create_task(self._run(), name="sora-automation-worker")

    def fence(self) -> None:
        # Synchronous: lifecycle acknowledgement fences admission before normal cleanup awaits.
        self.closing = True
        self._stop.set()

    async def stop(self) -> None:
        self.fence()
        if self.task is None:
            return
        if self.task.done():
            await asyncio.gather(self.task, return_exceptions=True)
            return
        try:
            await asyncio.wait_for(asyncio.shield(self.task), timeout=5)
        except TimeoutError:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    def _check_admission(self, behavior_provider: str) -> None:
        if self.closing or not self.runtime._started:
            raise AutomationConflict("AUTOMATION_STOPPING")
        if self.runtime.app_settings is not None:
            settings = self.runtime.app_settings.active
            settings.local_companion.require(("agent_delegation",))
            preference = settings.agents.for_provider(behavior_provider)
            if preference is not None and not preference.enabled:
                raise OperationAuthorizationError("Selected provider disabled")

    async def dispatch(self, occurrence: AutomationOccurrence) -> None:
        if occurrence.status != "reserved" or self.closing:
            return
        if occurrence.slot.decision_at > self.clock():
            return  # A wall-clock rollback must not admit a future persisted reservation.
        key = await self.runtime.repository.database.read(
            lambda db: self.admission.key_in(db, occurrence.occurrence_id)
        )
        behavior = occurrence.behavior
        deadline = time.monotonic() + 2

        def guard(db: sqlite3.Connection) -> None:
            if time.monotonic() >= deadline:
                raise AutomationConflict("AUTOMATION_ADMISSION_EXPIRED")
            self._check_admission(behavior.provider)
            if occurrence.slot.decision_at > self.clock():
                raise AutomationConflict("AUTOMATION_NOT_DUE")
            self.admission.guard_in(db, occurrence.occurrence_id, now=self.clock())

        def commit(db: sqlite3.Connection, receipt: SubmissionReceipt) -> None:
            self._check_admission(receipt.run.provider)
            if receipt.run.local_delegation_epoch != self.runtime._delegation_epoch():
                raise AutomationConflict("AUTOMATION_POLICY_CHANGED")
            self.admission.commit_in(db, occurrence.occurrence_id, receipt)

        try:
            with owner_local_scope():
                await asyncio.wait_for(
                    self.runtime.submit_task(
                        behavior.intent,
                        idempotency_key=key,
                        explicit_provider=behavior.provider,
                        explicit_model=behavior.model,
                        explicit_effort=behavior.effort,
                        working_directory=behavior.working_directory,
                        workspace_mode=behavior.workspace_mode,
                        _admission_guard=guard,
                        _admission_commit=commit,
                    ),
                    timeout=2,
                )
        except asyncio.CancelledError:
            raise  # Stop leaves an unadmitted reservation for conservative startup reconciliation.
        except AutomationConflict as error:
            if error.code not in {"AUTOMATION_STOPPING", "AUTOMATION_NOT_DUE"}:
                await self.admission.block(occurrence.occurrence_id, error.code.lower())
        except (
            OperationAuthorizationError,
            ProviderLaunchError,
            ValueError,
            RuntimeError,
            TimeoutError,
            OSError,
        ):
            # Do not expose provider errors, owner paths, prompt or model transcripts.
            # If commit succeeded before a later failure, block() sees evidence and does nothing.
            await self.admission.block(occurrence.occurrence_id, "admission_unavailable")

    async def tick(self) -> None:
        if self.started_at is None or self.closing:
            return
        async with self._tick_lock:
            if self.closing:
                return
            now = require_aware(self.clock(), "clock").astimezone(UTC)
            deadline = time.monotonic() + 5
            self.degraded = False
            rows = await self.runtime.repository.database.read(
                lambda db: db.execute(
                    "SELECT o.rowid AS ordinal,o.occurrence_id FROM automation_occurrences o "
                    "JOIN automation_definitions d ON d.automation_id=o.automation_id "
                    "WHERE d.owner_id=? AND (d.project_id IS NULL OR d.project_id=?) "
                    "AND o.status IN ('reserved','admitted','unknown') AND o.rowid>? "
                    "ORDER BY o.rowid LIMIT ?",
                    (self.store.owner, self.store.project, self._occurrence_after, self.batch_size),
                ).fetchall()
            )
            if not rows:
                self._occurrence_after = 0
            for row in rows:
                if self.closing:
                    return
                if time.monotonic() >= deadline:
                    break
                self._occurrence_after = int(row["ordinal"])
                try:
                    value = await self.admission.reconcile(
                        row["occurrence_id"], now=now, started_at=self.started_at
                    )
                    await self.dispatch(value)
                except (AutomationStorageError, sqlite3.Error, LookupError, ValueError):
                    self.degraded = True  # Bad record cannot kill timing or starve later records.

            definitions = await self.runtime.repository.database.read(
                lambda db: db.execute(
                    "SELECT rowid AS ordinal,* FROM automation_definitions WHERE owner_id=? "
                    "AND (project_id IS NULL OR project_id=?) AND state='active' AND rowid>? "
                    "ORDER BY rowid LIMIT ?",
                    (self.store.owner, self.store.project, self._definition_after, self.batch_size),
                ).fetchall()
            )
            if not definitions:
                self._definition_after = 0
            for row in definitions:
                if self.closing:
                    return
                if time.monotonic() >= deadline:
                    break
                self._definition_after = int(row["ordinal"])
                try:
                    definition, slot = self.store._decode(row)
                    if slot is None or slot.decision_at > now:
                        continue
                    reserved = await self.store.reserve_scheduled(
                        definition.automation_id,
                        definition.entity_version,
                        slot.slot_key,
                        now=now,
                        recovered=slot.decision_at < self.started_at,
                    )
                    if reserved is not None:
                        await self.dispatch(reserved)
                except AutomationConflict:
                    pass  # A concurrent owner edit won; read its next version on a later tick.
                except (
                    AutomationStorageError,
                    sqlite3.Error,
                    LookupError,
                    ValueError,
                    OverflowError,
                ):
                    self.degraded = True

    async def _run(self) -> None:
        while not self.closing:
            try:
                await self.tick()
            except Exception:
                # Keep the timing service alive without exposing private exception text.
                # Cancellation remains BaseException and is never swallowed here.
                self.degraded = True
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                pass
