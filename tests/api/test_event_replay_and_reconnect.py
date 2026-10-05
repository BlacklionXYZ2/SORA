"""Tests for event replay, reconnectable streams, deduplication, and backpressure (P08.2)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.models import EventEnvelope
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_websocket_streaming_and_reconnect_replay(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()

    token = "test-token-abcdef-123456"
    api_cfg = ApiServerConfig(
        host="127.0.0.1",
        port=0,
        auth_token=token,
        client_buffer_capacity=100,
        replay_limit=10,
    )
    server = SoraApiServer(runtime, api_cfg)
    await server.start()

    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token=token,
    )

    received_events: list[EventEnvelope] = []

    async def on_event(env: EventEnvelope) -> None:
        received_events.append(env)

    # Start client streaming task
    stream_task = asyncio.create_task(client.stream_events(on_event=on_event))
    await asyncio.sleep(0.1)  # allow WS handshake

    try:
        # Commit one message while connected: its event should stream live.
        await client.post_message("live-stream-message")
        await asyncio.sleep(0.2)
        assert len(received_events) >= 1
        seq_at_disconnect = client.last_sequence

        # Disconnect client
        client.stop_streaming()
        await stream_task

        # Create a durable offline backlog larger than three replay pages and let
        # the outbox pump mark it delivered before reconnect.
        for index in range(35):
            await client.post_message(f"offline-message-{index}")
        for _ in range(100):
            if not await runtime.runtime_repository.pending_outbox(limit=1):
                break
            await asyncio.sleep(0.01)
        assert not await runtime.runtime_repository.pending_outbox(limit=1)

        # Reconnect with cursor: should replay missed events
        replayed_events: list[EventEnvelope] = []

        async def on_replayed(env: EventEnvelope) -> None:
            replayed_events.append(env)

        reconnect_client = SoraApiClient(
            base_url=f"http://127.0.0.1:{server.actual_port}",
            auth_token=token,
        )
        reconnect_client.last_sequence = seq_at_disconnect

        reconnect_task = asyncio.create_task(reconnect_client.stream_events(on_event=on_replayed))
        for _ in range(100):
            if len(replayed_events) >= 35:
                break
            await asyncio.sleep(0.01)

        # Verify missed events were replayed in order
        assert len(replayed_events) == 35
        assert all(e.sequence > seq_at_disconnect for e in replayed_events)
        assert [event.sequence for event in replayed_events] == list(
            range(seq_at_disconnect + 1, seq_at_disconnect + 36)
        )

        reconnect_client.stop_streaming()
        await reconnect_task

    finally:
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
async def test_expired_cursor_triggers_resync(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()

    token = "test-token-abcdef-123456"
    api_cfg = ApiServerConfig(host="127.0.0.1", port=0, auth_token=token)
    server = SoraApiServer(runtime, api_cfg)
    await server.start()

    client = SoraApiClient(
        base_url=f"http://127.0.0.1:{server.actual_port}",
        auth_token=token,
    )

    resync_received: list[dict[str, Any]] = []

    async def on_resync(snap: dict[str, Any]) -> None:
        resync_received.append(snap)

    async def on_event(env: EventEnvelope) -> None:
        pass

    # Connect with an expired/invalid sequence (-99)
    client.last_sequence = -99
    stream_task = asyncio.create_task(client.stream_events(on_event=on_event, on_resync=on_resync))
    await asyncio.sleep(0.2)

    try:
        assert len(resync_received) == 1
        snapshot = resync_received[0]
        assert "owner_id" in snapshot
        assert "tasks" in snapshot
        assert "messages" in snapshot
    finally:
        client.stop_streaming()
        await stream_task
        await server.close()
        await runtime.close()
