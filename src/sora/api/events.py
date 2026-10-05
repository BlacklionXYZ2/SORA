"""Event streaming, replay, deduplication, and backpressure protection for SORA API."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sora.api.protocol import WebSocketSession
from sora.contracts.events import EventOrder, classify_event_order
from sora.contracts.models import EventEnvelope
from sora.runtime.service import SoraRuntime

logger = logging.getLogger(__name__)


@dataclass
class EventSubscription:
    """Represents an active WebSocket client event subscription."""

    client_id: str
    session: WebSocketSession
    stream_id: str
    queue: asyncio.Queue[dict[str, Any]]
    last_envelope: EventEnvelope | None = None
    last_sequence: int = 0
    connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBroadcaster:
    """Manages active WebSocket subscriptions and broadcasts events with backpressure."""

    def __init__(self, buffer_capacity: int = 100) -> None:
        self.buffer_capacity = buffer_capacity
        self._subscriptions: dict[str, EventSubscription] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        client_id: str,
        session: WebSocketSession,
        stream_id: str,
        last_sequence: int = 0,
        last_envelope: EventEnvelope | None = None,
    ) -> EventSubscription:
        sub = EventSubscription(
            client_id=client_id,
            session=session,
            stream_id=stream_id,
            queue=asyncio.Queue(maxsize=self.buffer_capacity),
            last_envelope=last_envelope,
            last_sequence=last_sequence,
        )
        async with self._lock:
            self._subscriptions[client_id] = sub
        return sub

    async def unregister(self, client_id: str) -> None:
        async with self._lock:
            self._subscriptions.pop(client_id, None)

    @property
    def active_client_count(self) -> int:
        return len(self._subscriptions)

    async def broadcast_event(self, envelope: EventEnvelope) -> None:
        """Publishes an event to all matching subscribers, disconnecting slow consumers."""
        slow_clients: list[EventSubscription] = []
        async with self._lock:
            subscribers = list(self._subscriptions.values())

        for sub in subscribers:
            if sub.stream_id != envelope.stream_id:
                continue

            if envelope.sequence <= sub.last_sequence:
                continue

            # Deduplication using contract order classifier
            order = classify_event_order(sub.last_envelope, envelope)
            if order == EventOrder.DUPLICATE:
                continue

            sub.last_envelope = envelope
            sub.last_sequence = envelope.sequence
            msg = {
                "type": "event",
                "envelope": envelope.model_dump(mode="json"),
            }

            try:
                sub.queue.put_nowait(msg)
            except asyncio.QueueFull:
                # P08.2 backpressure protection: slow client does not block Core
                logger.warning(
                    "Client %s buffer exceeded (%d items); disconnecting with policy violation",
                    sub.client_id,
                    self.buffer_capacity,
                )
                slow_clients.append(sub)

        for slow in slow_clients:
            await self.unregister(slow.client_id)
            try:
                await slow.session.send_close(
                    code=1008, reason="buffer_overflow_slow_client_backpressure"
                )
                await slow.session.close()
            except Exception:
                pass


async def replay_events_since(
    runtime: SoraRuntime,
    stream_id: str,
    since_sequence: int,
    limit: int = 500,
    through_sequence: int | None = None,
) -> list[EventEnvelope]:
    """Replays events from the persistent events table starting strictly after since_sequence."""

    def read(db: Any) -> list[dict[str, Any]]:
        if through_sequence is None:
            cursor = db.execute(
                "SELECT payload FROM events WHERE stream_id=? AND sequence > ? "
                "ORDER BY sequence ASC LIMIT ?",
                (stream_id, since_sequence, limit),
            )
        else:
            cursor = db.execute(
                "SELECT payload FROM events WHERE stream_id=? AND sequence > ? AND sequence <= ? "
                "ORDER BY sequence ASC LIMIT ?",
                (stream_id, since_sequence, through_sequence, limit),
            )
        return [json.loads(row[0]) for row in cursor.fetchall()]

    raw_payloads = await runtime.repository.database.read(read)
    return [EventEnvelope.model_validate(p) for p in raw_payloads]


async def get_stream_bounds(runtime: SoraRuntime, stream_id: str) -> tuple[int, int]:
    """Returns (min_sequence, max_sequence) for a stream, or (0, 0) if empty."""

    def read(db: Any) -> tuple[int, int]:
        row = db.execute(
            "SELECT COALESCE(MIN(sequence), 0), COALESCE(MAX(sequence), 0) "
            "FROM events WHERE stream_id=?",
            (stream_id,),
        ).fetchone()
        return int(row[0]), int(row[1])

    return await runtime.repository.database.read(read)


async def build_state_snapshot(
    runtime: SoraRuntime, stream_id: str, *, local: bool = True,
) -> dict[str, Any]:
    """Builds an authoritative state snapshot for client resynchronization."""
    owner_id = stream_id
    min_seq, max_seq = await get_stream_bounds(runtime, stream_id)

    # Fetch recent active tasks
    def read_tasks(db: Any) -> list[dict[str, Any]]:
        cursor = db.execute(
            "SELECT payload FROM tasks WHERE owner_id=? ORDER BY rowid DESC LIMIT 50",
            (owner_id,),
        )
        return [json.loads(row[0]) for row in cursor.fetchall()]

    tasks = await runtime.repository.database.read(read_tasks)
    if not local:
        for task in tasks:
            task.pop("working_directory", None)
            task.pop("workspace_base_ref", None)
            task.pop("companion_brief", None)

    # Fetch recent messages
    all_messages = await runtime.repository.list_messages(runtime.config.conversation_id)
    messages = all_messages[-50:]

    # Fetch active identity
    identity_rev = await runtime.repository.active_identity(owner_id)

    return {
        "owner_id": owner_id,
        "latest_sequence": max_seq,
        "identity_revision": identity_rev.content_hash if identity_rev else None,
        "tasks": tasks,
        "messages": [m.model_dump(mode="json") for m in messages],
        "timestamp": datetime.now(UTC).isoformat(),
    }
