"""Tests for embodiment API routes, projections, and command dispatch."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


@pytest_asyncio.fixture
async def api_handler(tmp_path: Path) -> AsyncIterator[RouteHandler]:
    cfg = RuntimeConfig(
        root=tmp_path / "runtime",
        identity_root=IDENTITY_ROOT,
    )
    provider = DeterministicProvider()
    runtime = SoraRuntime(cfg, provider=provider)
    await runtime.start()
    handler = RouteHandler(runtime)
    await persist_operation_grant(runtime, "embodiment.topology", grant_id="grant-topology")
    await persist_operation_grant(runtime, "embodiment.command", grant_id="grant-command")
    try:
        yield handler
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_embodiment_projection_and_topology_flow(api_handler: RouteHandler) -> None:
    # 1. Inspect initial embodiment projection
    req = HttpRequest("GET", "/api/v1/projections/embodiment", headers={}, body=b"")
    resp = await api_handler.handle_request(req)
    assert resp.status_code == 200
    data = resp.parse_json()
    assert data["revision"] == 1
    assert data["connected"] is False
    assert len(data["topology"]["monitors"]) == 1

    # 2. Update topology via API
    update_payload = {
        "monitors": [
            {
                "id": "DISPLAY1",
                "primary": True,
                "rect": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                "dpi_scale": 1.0,
                "orientation": "landscape",
            },
            {
                "id": "DISPLAY2",
                "primary": False,
                "rect": {"x": 1920, "y": 0, "width": 1920, "height": 1080},
                "dpi_scale": 1.0,
                "orientation": "landscape",
            },
        ]
    }
    req_top = HttpRequest(
        "POST",
        "/api/v1/embodiment/topology",
        headers={
            "Content-Type": "application/json",
            "X-SORA-Device-ID": "device-local",
            "X-SORA-Grant-ID": "grant-topology",
        },
        body=json.dumps(update_payload).encode("utf-8"),
    )
    resp_top = await api_handler.handle_request(req_top)
    assert resp_top.status_code == 200
    assert resp_top.parse_json()["status"] == "updated"
    assert resp_top.parse_json()["revision"] == 2

    # Verify updated projection
    resp2 = await api_handler.handle_request(req)
    assert resp2.parse_json()["revision"] == 2
    assert len(resp2.parse_json()["topology"]["monitors"]) == 2

    # 3. Dispatch embodiment command with valid revision
    cmd_queue = api_handler.runtime.register_embodiment_queue()
    cmd_payload = {
        "command_id": "cmd-001",
        "verb": "move_to",
        "target_point": {"x": 2500, "y": 500},
        "speed_px_per_sec": 200.0,
        "topology_revision": 2,
        "created_at": datetime.now(UTC).isoformat(),
    }
    req_cmd = HttpRequest(
        "POST",
        "/api/v1/embodiment/command",
        headers={
            "Content-Type": "application/json",
            "X-SORA-Device-ID": "device-local",
            "X-SORA-Grant-ID": "grant-command",
        },
        body=json.dumps(cmd_payload).encode("utf-8"),
    )
    resp_cmd = await api_handler.handle_request(req_cmd)
    assert resp_cmd.status_code == 200
    assert resp_cmd.parse_json()["status"] == "queued"

    # Verify received on queue
    dispatched_cmd = cmd_queue.get_nowait()
    assert dispatched_cmd.command_id == "cmd-001"
    assert dispatched_cmd.target_point is not None
    assert dispatched_cmd.target_point.x == 2500

    # 4. Dispatch with stale revision -> 409 Conflict
    stale_cmd_payload = dict(cmd_payload, command_id="cmd-002", topology_revision=1)
    req_stale = HttpRequest(
        "POST",
        "/api/v1/embodiment/command",
        headers={"Content-Type": "application/json"},
        body=json.dumps(stale_cmd_payload).encode("utf-8"),
    )
    resp_stale = await api_handler.handle_request(req_stale)
    assert resp_stale.status_code == 409
    assert resp_stale.parse_json()["error"]["code"] == "STALE_TOPOLOGY_REVISION"
