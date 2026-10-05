"""Tests for client supervision, independent disconnect,
and multi-client state convergence (P08.4 & G3 DoD).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sora.api import ApiServerConfig, SoraApiClient, SoraApiServer
from sora.contracts.models import EventEnvelope
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_independent_client_lifecycle_and_multi_client_convergence(tmp_path: Path) -> None:
    """G3 DoD: Two authenticated clients share consistent state,
    recover events, and disconnect independently.
    """
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

    client_a = SoraApiClient(base_url=f"http://127.0.0.1:{server.actual_port}", auth_token=token)
    client_b = SoraApiClient(base_url=f"http://127.0.0.1:{server.actual_port}", auth_token=token)

    events_a: list[EventEnvelope] = []
    events_b: list[EventEnvelope] = []

    async def on_event_a(env: EventEnvelope) -> None:
        events_a.append(env)

    async def on_event_b(env: EventEnvelope) -> None:
        events_b.append(env)

    task_stream_a = asyncio.create_task(client_a.stream_events(on_event=on_event_a))
    task_stream_b = asyncio.create_task(client_b.stream_events(on_event=on_event_b))
    await asyncio.sleep(0.1)

    try:
        # Both clients submit tasks
        await client_a.submit_task("Task from Client A")
        await client_b.submit_task("Task from Client B")
        await asyncio.sleep(0.3)

        # Both clients receive streamed events
        assert len(events_a) >= 2
        assert len(events_b) >= 2

        # Client A disconnects independently; Client B remains connected and functional
        client_a.stop_streaming()
        await task_stream_a

        # Client B submits another task
        await client_b.submit_task("Task 3 while A is offline")
        await asyncio.sleep(0.3)
        assert len(events_b) > len(events_a)

        # Client A reconnects with replay cursor; catches up and converges with Client B
        replayed_a: list[EventEnvelope] = []

        async def on_reconnect_a(env: EventEnvelope) -> None:
            replayed_a.append(env)

        reconnect_task_a = asyncio.create_task(client_a.stream_events(on_event=on_reconnect_a))
        await asyncio.sleep(0.3)

        total_a_events = len(events_a) + len(replayed_a)
        assert total_a_events == len(events_b)

        # Both clients verify identical projections
        proj_a = await client_a.get_objects_projection()
        proj_b = await client_b.get_objects_projection()
        assert proj_a == proj_b

        client_a.stop_streaming()
        client_b.stop_streaming()
        await reconnect_task_a
        await task_stream_b

    finally:
        await server.close()
        await runtime.close()
