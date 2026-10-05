"""P13.2 scoped one-shot capture, retention, revocation, and native acceptance."""

from __future__ import annotations

import asyncio
import base64
import json
import os
import struct
import sys
import zlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.capture import (
    DesktopCaptureFrame,
    DesktopCaptureRequest,
    DesktopCaptureSource,
    DesktopCaptureStatus,
)
from sora.contracts.desktop import DesktopObservationRequest, DesktopTargetRequest
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.models import CapabilityOperation, GrantStatus
from sora.desktop.capture import WindowsCaptureBridge, WindowsCaptureReply, WindowsCaptureRequest
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError
from sora.vision import DesktopCaptureStore, decode_png_frame

ROOT = Path(__file__).resolve().parents[2]


def png(width: int, height: int, rgba: tuple[int, int, int, int] = (12, 34, 56, 255)) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(b"\x00" + bytes(rgba) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def reply_for(region: ScreenRect, *, now: datetime | None = None) -> WindowsCaptureReply:
    return WindowsCaptureReply(
        status=DesktopCaptureStatus.OK,
        captured_at=now or datetime.now(UTC),
        region=region,
        png_base64=base64.b64encode(png(region.width, region.height)).decode(),
    )


class FakeCaptureBridge(WindowsCaptureBridge):
    def __init__(self, reply: WindowsCaptureReply) -> None:
        self.reply = reply
        self.requests: list[WindowsCaptureRequest] = []
        self.started = asyncio.Event()
        self.release: asyncio.Event | None = None
        self.cancelled = False

    async def capture(self, request: WindowsCaptureRequest) -> WindowsCaptureReply:
        self.requests.append(request)
        self.started.set()
        try:
            if self.release is not None:
                await self.release.wait()
            return self.reply
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    instance = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await instance.start()
    try:
        yield instance
    finally:
        await instance.close()


def make_frame(
    capture_id: str, at: datetime, width: int = 2, height: int = 2
) -> DesktopCaptureFrame:
    image = png(width, height)
    import hashlib

    return DesktopCaptureFrame(
        capture_id=capture_id,
        source=DesktopCaptureSource.REGION,
        captured_at=at,
        expires_at=at + timedelta(seconds=5),
        topology_revision=1,
        region=ScreenRect(x=10, y=10, width=width, height=height),
        byte_length=len(image),
        sha256=hashlib.sha256(image).hexdigest(),
        image_base64=base64.b64encode(image).decode(),
    )


def test_contract_scope_and_volatile_store_bounds() -> None:
    now = datetime.now(UTC)
    region = ScreenRect(x=10, y=20, width=2, height=2)
    request = DesktopCaptureRequest(
        capture_id="capture-region",
        source=DesktopCaptureSource.REGION,
        topology_revision=7,
        region=region,
    )
    assert request.resource == "desktop.capture:region:7:10,20,2,2"
    with pytest.raises(ValueError):
        DesktopCaptureRequest(
            capture_id="capture-too-wide",
            source=DesktopCaptureSource.REGION,
            topology_revision=7,
            region=region,
            desktop_target_id="target-forbidden",
        )

    store = DesktopCaptureStore(capacity=1, max_total_bytes=1024)
    first = make_frame("capture-first", now)
    second = make_frame("capture-second", now + timedelta(milliseconds=1))
    store.put(
        first,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert decode_png_frame(first) == png(2, 2)
    assert store.get(
        first.capture_id,
        owner_id="owner-local",
        device_id="other-device",
        project_id="project-sora",
        now=now,
    ) is None
    store.put(
        second,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    )
    assert store.count == 1
    assert store.get(
        first.capture_id,
        owner_id="owner-local",
        device_id="device-local",
        project_id="project-sora",
        now=now,
    ) is None
    assert store.prune(now + timedelta(seconds=6)) == 1
    assert store.count == store.total_bytes == 0


@pytest.mark.asyncio
async def test_exact_region_capture_api_and_no_widening(runtime: SoraRuntime) -> None:
    region = ScreenRect(x=10, y=20, width=3, height=2)
    capture_request = DesktopCaptureRequest(
        capture_id="capture-api-region",
        source=DesktopCaptureSource.REGION,
        topology_revision=1,
        region=region,
    )
    bridge = FakeCaptureBridge(reply_for(region))
    runtime.windows_capture_bridge = bridge
    authorization = await persist_operation_grant(
        runtime,
        capture_request.resource,
        grant_id="grant-capture-region",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    handler = RouteHandler(runtime)
    response = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/capture",
            headers={
                "x-sora-grant-id": "grant-capture-region",
                "x-sora-device-id": "device-local",
            },
            body=capture_request.model_dump_json().encode(),
        )
    )
    assert response.status_code == 200
    payload = response.parse_json()
    assert payload["status"] == "ok"
    assert payload["frame"]["region"] == region.model_dump(mode="json")
    assert bridge.requests[0].region == region
    assert runtime.desktop_captures.count == 1
    grant = await runtime.repository.get_grant(authorization.grant.grant_id)
    assert grant is not None and grant.used_count == 0

    widened = FakeCaptureBridge(reply_for(ScreenRect(x=10, y=20, width=4, height=2)))
    runtime.windows_capture_bridge = widened
    second_request = capture_request.model_copy(update={"capture_id": "capture-widened"})
    await persist_operation_grant(
        runtime,
        second_request.resource,
        grant_id="grant-capture-widened",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    rejected = await runtime.capture_desktop(
        second_request,
        grant_id="grant-capture-widened",
        device_id="device-local",
    )
    assert rejected.status is DesktopCaptureStatus.PROTOCOL_ERROR
    assert runtime.desktop_captures.count == 1


@pytest.mark.asyncio
async def test_invalid_scope_and_region_fail_before_side_effect(runtime: SoraRuntime) -> None:
    request = DesktopCaptureRequest(
        capture_id="capture-offscreen",
        source=DesktopCaptureSource.REGION,
        topology_revision=1,
        region=ScreenRect(x=5000, y=5000, width=10, height=10),
    )
    bridge = FakeCaptureBridge(reply_for(ScreenRect(x=5000, y=5000, width=10, height=10)))
    runtime.windows_capture_bridge = bridge
    authorization = await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-capture-offscreen",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    with pytest.raises(ValueError, match="active display"):
        await runtime.capture_desktop(
            request,
            grant_id="grant-capture-offscreen",
            device_id="device-local",
        )
    grant = await runtime.repository.get_grant(authorization.grant.grant_id)
    assert grant is not None and grant.used_count == 0
    assert not bridge.requests


@pytest.mark.asyncio
async def test_revocation_cancels_inflight_capture_and_retains_nothing(
    runtime: SoraRuntime,
) -> None:
    region = ScreenRect(x=20, y=20, width=2, height=2)
    request = DesktopCaptureRequest(
        capture_id="capture-revoked",
        source=DesktopCaptureSource.REGION,
        topology_revision=1,
        region=region,
    )
    bridge = FakeCaptureBridge(reply_for(region))
    bridge.release = asyncio.Event()
    runtime.windows_capture_bridge = bridge
    authorization = await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-capture-revoked",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    task = asyncio.create_task(
        runtime.capture_desktop(
            request,
            grant_id="grant-capture-revoked",
            device_id="device-local",
        )
    )
    await bridge.started.wait()
    await runtime.repository.save_grant(
        authorization.grant.model_copy(update={"status": GrantStatus.REVOKED})
    )
    with pytest.raises(OperationAuthorizationError):
        await asyncio.wait_for(task, timeout=1)
    assert bridge.cancelled
    assert runtime.desktop_captures.count == 0


@pytest.mark.asyncio
async def test_topology_change_discards_frame_and_clears_store(runtime: SoraRuntime) -> None:
    region = ScreenRect(x=20, y=20, width=2, height=2)
    request = DesktopCaptureRequest(
        capture_id="capture-old-layout",
        source=DesktopCaptureSource.REGION,
        topology_revision=1,
        region=region,
    )
    bridge = FakeCaptureBridge(reply_for(region))
    bridge.release = asyncio.Event()
    runtime.windows_capture_bridge = bridge
    await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-capture-layout",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    task = asyncio.create_task(
        runtime.capture_desktop(
            request,
            grant_id="grant-capture-layout",
            device_id="device-local",
        )
    )
    await bridge.started.wait()
    retained = make_frame("capture-before-layout-change", datetime.now(UTC))
    runtime.desktop_captures.put(
        retained,
        owner_id=runtime.config.owner_id,
        device_id="device-local",
        project_id=runtime.config.project_id,
    )
    assert runtime.desktop_captures.count == 1
    monitor = MonitorDescriptor(
        id="changed",
        primary=True,
        rect=ScreenRect(x=0, y=0, width=1280, height=720),
    )
    runtime.update_embodiment_topology((monitor,))
    bridge.release.set()
    result = await task
    assert result.status is DesktopCaptureStatus.STALE_LAYOUT
    assert runtime.desktop_captures.count == 0


@pytest.mark.asyncio
async def test_capture_bridge_timeout_protocol_and_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = asyncio.create_subprocess_exec
    children: list[asyncio.subprocess.Process] = []

    async def launch(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        script = "import sys,time;sys.stdin.readline();time.sleep(60)"
        process = await original(sys.executable, "-c", script, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    bridge = WindowsCaptureBridge(Path(sys.executable), timeout=0.2)
    request = WindowsCaptureRequest(
        capture_id="capture-timeout",
        source=DesktopCaptureSource.REGION,
        region=ScreenRect(x=0, y=0, width=1, height=1),
    )
    assert (await bridge.capture(request)).status is DesktopCaptureStatus.TIMEOUT
    assert children[0].returncode is not None

    task = asyncio.create_task(bridge.capture(request))
    async with asyncio.timeout(1):
        while len(children) < 2:
            await asyncio.sleep(0.005)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert children[1].returncode is not None


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("SORA_TEST_UIA") != "1", reason="opt-in native capture fixture")
async def test_real_window_and_region_capture(tmp_path: Path) -> None:
    capture_worker = (
        ROOT / "clients/windows_capture/bin/Debug/net10.0-windows/windows_capture.exe"
    )
    observation_worker = (
        ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    )
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    evidence = tmp_path / "capture-fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence))
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=ROOT / "identity",
            windows_bridge_executable=observation_worker,
            windows_capture_executable=capture_worker,
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        async with asyncio.timeout(10):
            while not evidence.exists():
                await asyncio.sleep(0.05)
        fixture_data = json.loads(evidence.read_text())
        observation_request = DesktopObservationRequest(
            operation="tree",
            process_id=process.pid,
            window_handle=fixture_data["hwnd"],
        )
        await persist_operation_grant(
            runtime,
            observation_request.resource,
            grant_id="grant-native-observation",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        observation = await runtime.observe_desktop(
            observation_request,
            grant_id="grant-native-observation",
            device_id="device-local",
        )
        button = next(node for node in observation.nodes if node.name == "Confirm fixture")
        assert button.rect is not None
        target = runtime.desktop_targets.issue(
            DesktopTargetRequest(
                process_id=process.pid,
                window_handle=fixture_data["hwnd"],
                runtime_id=button.runtime_id,
                automation_id=button.automation_id,
                control_type=button.control_type,
            ),
            observation,
            owner_id=runtime.config.owner_id,
            device_id="device-local",
            project_id=runtime.config.project_id,
        )

        window_request = DesktopCaptureRequest(
            capture_id="capture-native-window",
            source=DesktopCaptureSource.WINDOW,
            topology_revision=1,
            desktop_target_id=target.target_id,
        )
        await persist_operation_grant(
            runtime,
            window_request.resource,
            grant_id="grant-native-window",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        window_result = await runtime.capture_desktop(
            window_request,
            grant_id="grant-native-window",
            device_id="device-local",
        )
        assert window_result.status is DesktopCaptureStatus.OK
        assert window_result.frame is not None
        assert decode_png_frame(window_result.frame)
        assert window_result.frame.desktop_target_id == target.target_id

        region_request = DesktopCaptureRequest(
            capture_id="capture-native-region",
            source=DesktopCaptureSource.REGION,
            topology_revision=1,
            region=button.rect,
        )
        await persist_operation_grant(
            runtime,
            region_request.resource,
            grant_id="grant-native-region",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        region_result = await runtime.capture_desktop(
            region_request,
            grant_id="grant-native-region",
            device_id="device-local",
        )
        assert region_result.status is DesktopCaptureStatus.OK
        assert region_result.frame is not None
        assert region_result.frame.region == button.rect
        assert decode_png_frame(region_result.frame)
        assert runtime.desktop_captures.count == 2
    finally:
        await runtime.close()
        if process.returncode is None:
            process.kill()
        await process.wait()
