"""Ephemeral host registry and bounded semantic requests; ACK, never dispatch, is success."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sora.contracts.ui_presentation import (
    PresentationReason,
    PresentationStatus,
    UiHostCommand,
    UiHostLease,
    UiHostRegistration,
    UiMemoryCommand,
    UiMemoryPresentation,
    UiPresentationAck,
    UiPresentationPage,
    UiPresentationResult,
)
from sora.persistence.repository import SoraRepository
from sora.runtime.memory_browser import memory_detail


class UiPresentationError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class Host:
    lease: UiHostLease
    profile: str
    deadline: float


@dataclass
class Pending:
    request: UiMemoryPresentation
    deadline: float
    result: UiPresentationResult
    acknowledgement: UiPresentationAck | None = None


class MemoryPresentationHub:
    def __init__(self, repository: SoraRepository, owner: str, project: str | None):
        self.repository = repository
        self.owner, self.project = owner, project
        self.instance: str | None = None
        self.host: Host | None = None
        self.requests: OrderedDict[uuid.UUID, Pending] = OrderedDict()
        self.lock = asyncio.Lock()

    def bind(self, instance: str) -> None:
        if instance != self.instance:
            self.instance = instance
            self.host = None
            self.requests.clear()  # Old Core/host bindings are never replayable.

    def _prune(self) -> None:
        now = time.monotonic()
        if self.host is not None and now >= self.host.deadline:
            self.host = None
        for item in self.requests.values():
            if item.result.status == "pending" and (now >= item.deadline or self.host is None):
                item.result = item.result.model_copy(
                    update={
                        "status": "expired" if now >= item.deadline else "unavailable",
                        "reason": "deadline" if now >= item.deadline else "host-lost",
                    }
                )
        # Admission bounds unresolved requests; retain historical results for five minutes.
        for key in list(self.requests):
            if now - self.requests[key].deadline > 300:
                del self.requests[key]

    def _instance(self, value: uuid.UUID) -> None:
        if str(value) != self.instance:
            raise UiPresentationError("UI_CORE_CHANGED")

    def register(self, command: UiHostRegistration) -> UiHostLease:
        self._instance(command.instance_id)
        self._prune()
        if command.panels != ("memory",):
            raise UiPresentationError("UI_UNSUPPORTED_REGISTRY")
        if self.host is not None:
            lease = self.host.lease
            if command.host_id != lease.host_id or command.profile_key != self.host.profile:
                raise UiPresentationError("UI_HOST_CONFLICT")
            if (
                command.lease_id not in {None, lease.lease_id}
                or command.registry_generation < lease.registry_generation
            ):
                raise UiPresentationError("UI_STALE_REGISTRY")
        else:
            lease = UiHostLease(
                instance_id=command.instance_id,
                host_id=command.host_id,
                lease_id=uuid.uuid4(),
                registry_generation=command.registry_generation,
                expires_at=datetime.now(UTC) + timedelta(seconds=30),
            )
        lease = lease.model_copy(
            update={
                "registry_generation": command.registry_generation,
                "expires_at": datetime.now(UTC) + timedelta(seconds=30),
            }
        )
        self.host = Host(lease, command.profile_key, time.monotonic() + 30)
        return lease

    def _host(self, command: UiHostCommand) -> Host:
        self._instance(command.instance_id)
        self._prune()
        host = self.host
        if (
            host is None
            or host.lease.host_id != command.host_id
            or host.lease.lease_id != command.lease_id
        ):
            raise UiPresentationError("UI_HOST_UNAVAILABLE")
        return host

    def poll(self, command: UiHostCommand) -> UiPresentationPage:
        host = self._host(command)
        requests = tuple(
            item.request
            for item in self.requests.values()
            if item.result.status == "pending" and item.request.lease_id == host.lease.lease_id
        )[:16]
        return UiPresentationPage(**command.model_dump(), requests=requests)

    async def _target(self, command: UiMemoryCommand) -> None:
        detail = await self.repository.database.read(
            lambda db: memory_detail(
                db,
                owner=self.owner,
                project_id=self.project,
                memory_id=command.memory_id,
                instance=str(command.instance_id),
                device="device-local",
                references=(),
            )
        )
        if detail.memory.entity_version != command.expected_version:
            raise UiPresentationError("UI_TARGET_CHANGED")

    async def request(
        self,
        command: UiMemoryCommand,
        *,
        companion: bool = False,
        dialogue_request_id: str | None = None,
        passive: bool = False,
    ) -> UiPresentationResult:
        self._instance(command.instance_id)
        self._prune()
        previous = self.requests.get(command.request_id)
        if previous is not None:
            if (
                previous.request.memory_id != command.memory_id
                or previous.request.expected_version != command.expected_version
                or previous.request.origin != ("companion" if companion else "owner")
                or previous.request.activation != ("passive" if passive else "explicit")
                or previous.request.dialogue_request_id != dialogue_request_id
            ):
                raise UiPresentationError("UI_REQUEST_CONFLICT")
            return previous.result
        await self._target(command)
        self._instance(command.instance_id)
        self._prune()
        # A concurrent admission may have completed during the canonical read.
        if command.request_id in self.requests:
            return await self.request(
                command,
                companion=companion,
                dialogue_request_id=dialogue_request_id,
                passive=passive,
            )
        if self.host is None:
            raise UiPresentationError("UI_HOST_UNAVAILABLE")
        if (
            len(self.requests) >= 256
            or sum(x.result.status == "pending" for x in self.requests.values()) >= 32
        ):
            raise UiPresentationError("UI_QUEUE_FULL")
        lease = self.host.lease
        request = UiMemoryPresentation(
            **command.model_dump(),
            host_id=lease.host_id,
            lease_id=lease.lease_id,
            registry_generation=lease.registry_generation,
            origin="companion" if companion else "owner",
            activation="passive" if passive else "explicit",
            dialogue_request_id=dialogue_request_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=15),
        )
        result = UiPresentationResult(
            instance_id=command.instance_id,
            request_id=command.request_id,
            memory_id=command.memory_id,
            expected_version=command.expected_version,
            status="pending",
            reason="queued",
            dialogue_request_id=dialogue_request_id,
        )
        self.requests[command.request_id] = Pending(request, time.monotonic() + 15, result)
        return result

    def result(self, request_id: uuid.UUID) -> UiPresentationResult:
        self._prune()
        item = self.requests.get(request_id)
        if item is None:
            raise LookupError("Presentation not found")
        return item.result

    def cancel(self, request_id: uuid.UUID) -> None:
        item = self.requests.get(request_id)
        if item is not None and item.result.status == "pending":
            item.result = item.result.model_copy(
                update={"status": "rejected", "reason": "turn-cancelled"}
            )

    async def acknowledge(self, command: UiPresentationAck) -> UiPresentationResult:
        async with self.lock:
            self._host(command)
            item = self.requests.get(command.request_id)
            if item is None:
                raise LookupError("Presentation not found")
            requested = item.request
            if (
                command.memory_id != requested.memory_id
                or command.expected_version != requested.expected_version
                or command.host_id != requested.host_id
                or command.lease_id != requested.lease_id
                or command.registry_generation < requested.registry_generation
            ):
                raise UiPresentationError("UI_ACK_MISMATCH")
            if item.acknowledgement is not None:
                if item.acknowledgement != command:
                    raise UiPresentationError("UI_ACK_CONFLICT")
                return item.result
            if item.result.status != "pending":
                return item.result  # Expired/lost requests never become successful later.
            if (
                self.host is not None
                and command.registry_generation < self.host.lease.registry_generation
            ):
                raise UiPresentationError("UI_STALE_REGISTRY")
            success = command.status in {"selected", "already-visible"}
            if success and (
                not command.panel_visible
                or not command.highlighted
                or command.selected_id != command.memory_id
                or command.selected_version != command.expected_version
                or command.anchor is None
            ):
                raise UiPresentationError("UI_ACK_MISMATCH")
            if not success and (command.highlighted or command.anchor is not None):
                raise UiPresentationError("UI_ACK_MISMATCH")

            def write(db: sqlite3.Connection) -> UiPresentationResult:
                # Atomic target check/event commit; the UI claim is not OS attestation.
                if item.result.status != "pending":
                    return item.result
                host = self.host
                now = time.monotonic()
                if now >= item.deadline:
                    return item.result.model_copy(
                        update={"status": "expired", "reason": "deadline"}
                    )
                if (
                    self.instance != str(command.instance_id)
                    or host is None
                    or now >= host.deadline
                    or host.lease.lease_id != command.lease_id
                    or command.registry_generation < host.lease.registry_generation
                ):
                    return item.result.model_copy(
                        update={"status": "unavailable", "reason": "host-lost"}
                    )
                status: PresentationStatus = command.status
                reasons: dict[str, PresentationReason] = {
                    "selected": "host-acknowledged",
                    "already-visible": "host-acknowledged",
                    "deferred": "host-deferred",
                    "unavailable": "host-unavailable",
                    "rejected": "host-rejected",
                }
                reason = reasons[status]
                if success:
                    row = db.execute(
                        "SELECT entity_version FROM memories WHERE memory_id=? AND owner_id=? "
                        "AND (project_id IS NULL OR project_id=?) AND deleted_at IS NULL",
                        (command.memory_id, self.owner, self.project),
                    ).fetchone()
                    if row is None or row[0] != command.expected_version:
                        status, reason = "unavailable", "target-changed"
                revision = int(
                    db.execute("SELECT revision FROM state_meta WHERE singleton=1").fetchone()[0]
                )
                event_id = self.repository._append_event(
                    db,
                    self.owner,
                    revision,
                    "ui.memory.presented",
                    None,
                    None,
                    {
                        "request_id": str(command.request_id),
                        "memory_id": command.memory_id,
                        "entity_version": command.expected_version,
                        "status": status,
                        "host_id": str(command.host_id),
                        "instance_id": str(command.instance_id),
                        "registry_generation": command.registry_generation,
                        "dialogue_request_id": requested.dialogue_request_id,
                    },
                )
                return UiPresentationResult(
                    instance_id=command.instance_id,
                    request_id=command.request_id,
                    memory_id=command.memory_id,
                    expected_version=command.expected_version,
                    status=status,
                    reason=reason,
                    event_id=event_id,
                    registry_generation=command.registry_generation,
                    dialogue_request_id=requested.dialogue_request_id,
                )

            pending_write = asyncio.create_task(self.repository.database.write(write))
            try:
                result = await asyncio.shield(pending_write)
            except asyncio.CancelledError:
                item.result = await pending_write
                item.acknowledgement = command
                raise
            item.result = result
            item.acknowledgement = command
            return result
