"""Core grants, observation API, and real Windows fixture acceptance."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.desktop import (
    DesktopAuthority,
    DesktopObservation,
    DesktopObservationRequest,
    DesktopPresentationVerb,
    DesktopTargetRequest,
)
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.models import CapabilityOperation, GrantStatus
from sora.desktop.bridge import WindowsObservationBridge
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError

ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        yield runtime
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_exact_scope_revocation_and_api(runtime: SoraRuntime) -> None:
    request = DesktopObservationRequest(operation="windows", process_id=123)
    args = {"grant_id": "grant-observe", "device_id": "device-local"}
    with pytest.raises(OperationAuthorizationError):
        await runtime.observe_desktop(request, **args)
    await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-generic-tool",
    )
    with pytest.raises(OperationAuthorizationError):
        await runtime.observe_desktop(
            request,
            grant_id="grant-generic-tool",
            device_id="device-local",
        )
    await persist_operation_grant(
        runtime,
        "desktop.observe:124",
        grant_id="grant-observe",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    with pytest.raises(OperationAuthorizationError):
        await runtime.observe_desktop(request, **args)
    auth = await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-observe",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )
    assert (await runtime.observe_desktop(request, **args)).status == "not_configured"
    handler = RouteHandler(runtime)
    api_request = HttpRequest(
        "POST",
        "/api/v1/desktop/observe",
        headers={"x-sora-grant-id": "grant-observe", "x-sora-device-id": "device-local"},
        body=request.model_dump_json().encode(),
    )
    allowed = await handler.handle_request(api_request)
    assert allowed.status_code == 200 and allowed.parse_json()["status"] == "not_configured"
    with pytest.raises(OperationAuthorizationError):
        await runtime.observe_desktop(request, grant_id="grant-observe", device_id="other")
    await runtime.repository.save_grant(
        auth.grant.model_copy(update={"status": GrantStatus.REVOKED})
    )
    handler = RouteHandler(runtime)
    response = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/observe",
            headers={"x-sora-grant-id": "grant-observe", "x-sora-device-id": "device-local"},
            body=request.model_dump_json().encode(),
        )
    )
    assert response.status_code == 403
    invalid = await handler.handle_request(
        HttpRequest(
            "POST",
            "/api/v1/desktop/observe",
            headers={},
            body=b'{"operation":"invoke"}',
        )
    )
    assert invalid.status_code == 400


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("SORA_TEST_UIA") != "1", reason="opt-in real Windows UIA fixture")
async def test_real_windows_fixture(runtime: SoraRuntime, tmp_path: Path) -> None:
    worker = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    evidence = tmp_path / "fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence))
    runtime.windows_bridge = WindowsObservationBridge(worker)
    try:
        async with asyncio.timeout(10):
            while not evidence.exists():
                await asyncio.sleep(0.05)
        fixture_data = json.loads(evidence.read_text())
        request = DesktopObservationRequest(operation="windows", process_id=process.pid)
        auth = await persist_operation_grant(
            runtime,
            request.resource,
            grant_id="grant-uia",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        # Finite budget proves accounting occurs before the observation worker runs.
        await runtime.repository.save_grant(auth.grant.model_copy(update={"max_uses": 7}))
        args = {"grant_id": "grant-uia", "device_id": "device-local"}
        windows = await runtime.observe_desktop(request, **args)
        assert windows.status == "ok"
        assert any(n.window_handle == fixture_data["hwnd"] for n in windows.nodes)
        tree_request = DesktopObservationRequest(
            operation="tree",
            process_id=process.pid,
            window_handle=fixture_data["hwnd"],
        )
        tree = await runtime.observe_desktop(tree_request, **args)
        assert tree.status == "ok", tree
        button = next(n for n in tree.nodes if n.name == "Confirm fixture")
        assert button.control_type == "ControlType.Button"
        assert button.rect is not None
        for field in ("x", "y", "width", "height"):
            assert abs(getattr(button.rect, field) - fixture_data["button"][field]) <= 1
        password = next(n for n in tree.nodes if n.password)
        assert not password.name
        assert "never-export-this" not in tree.model_dump_json()

        # P10.2: acquire and independently revalidate the native UIA identity.
        target = await runtime.acquire_desktop_target(
            DesktopTargetRequest(
                process_id=process.pid,
                window_handle=fixture_data["hwnd"],
                runtime_id=button.runtime_id,
                automation_id=button.automation_id,
                control_type=button.control_type,
            ),
            **args,
        )
        assert target.process_started_at == tree.process_started_at
        assert target.runtime_id == button.runtime_id
        await persist_operation_grant(
            runtime,
            f"desktop.present:{target.target_id}",
            grant_id="grant-uia-present",
            operation=CapabilityOperation.DESKTOP_PRESENT,
        )
        revalidated = await runtime.revalidate_desktop_target(
            target.target_id,
            authority=DesktopAuthority.PRESENT,
            grant_id="grant-uia-present",
            device_id="device-local",
        )
        assert revalidated.rect == target.rect
        presentation_queue = runtime.register_embodiment_queue()
        point_command = await runtime.present_desktop_target(
            target.target_id,
            verb=DesktopPresentationVerb.POINT,
            grant_id="grant-uia-present",
            device_id="device-local",
        )
        assert presentation_queue.get_nowait() == point_command
        assert point_command.target_rect == button.rect
        assert point_command.target_id == target.target_id

        bounded = await runtime.observe_desktop(
            tree_request.model_copy(update={"max_nodes": 1}),
            **args,
        )
        assert len(bounded.nodes) == 1 and bounded.truncated
        wrong = await runtime.observe_desktop(
            tree_request.model_copy(update={"window_handle": 1}),
            **args,
        )
        assert wrong.status == "unavailable"
        evidence.with_suffix(".json.hang").touch()
        await asyncio.sleep(0.3)
        timeout = await runtime.observe_desktop(tree_request, **args)
        assert timeout.status == "timeout"
        # Core remains responsive after observing the hung provider.
        assert runtime.topology_manager.revision == tree.topology_revision
        grant = await runtime.repository.get_grant("grant-uia")
        assert grant is not None and grant.used_count == 6
        process.kill()
        await process.wait()

        closed = await runtime.observe_desktop(tree_request, **args)
        assert closed.status == "unavailable"
        grant = await runtime.repository.get_grant("grant-uia")
        assert grant is not None and grant.used_count == 7
        with pytest.raises(OperationAuthorizationError):
            await runtime.observe_desktop(tree_request, **args)
        out = ROOT / ".local/p10-uia-evidence"
        out.mkdir(parents=True, exist_ok=True)
        (out / "fixture-acceptance.json").write_text(
            json.dumps(
                {
                    "windows": windows.model_dump(mode="json"),
                    "tree": tree.model_dump(mode="json"),
                    "expected_button": fixture_data["button"],
                    "hung_status": timeout.status,
                    "grant_uses": grant.used_count,
                    "closed_status": closed.status,
                    "desktop_target": target.model_dump(mode="json"),
                    "point_command": point_command.model_dump(mode="json"),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_ELEVATED_PID") or not os.getenv("SORA_TEST_INACCESSIBLE_PID"),
    reason="opt-in live elevated/inaccessible process matrix",
)
async def test_live_elevated_and_inaccessible_process_matrix() -> None:
    worker = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    bridge = WindowsObservationBridge(worker, timeout=2)
    elevated_pid = int(os.environ["SORA_TEST_ELEVATED_PID"])
    inaccessible_pid = int(os.environ["SORA_TEST_INACCESSIBLE_PID"])
    elevated = await asyncio.wait_for(
        bridge.observe(DesktopObservationRequest(operation="windows", process_id=elevated_pid)),
        timeout=3,
    )
    inaccessible = await asyncio.wait_for(
        bridge.observe(DesktopObservationRequest(operation="windows", process_id=inaccessible_pid)),
        timeout=3,
    )
    assert elevated.status == "elevated_target"
    assert inaccessible.status == "access_denied"
    assert not elevated.nodes and not inaccessible.nodes


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["revocation", "layout"])
async def test_inflight_changes_discard_observation(runtime: SoraRuntime, change: str) -> None:
    request = DesktopObservationRequest(operation="windows", process_id=123)
    auth = await persist_operation_grant(
        runtime,
        request.resource,
        grant_id="grant-inflight",
        operation=CapabilityOperation.DESKTOP_OBSERVE,
    )

    class ChangingBridge(WindowsObservationBridge):
        async def observe(self, request: DesktopObservationRequest) -> DesktopObservation:
            if change == "revocation":
                await runtime.repository.save_grant(
                    auth.grant.model_copy(update={"status": GrantStatus.REVOKED})
                )
            else:
                rect = ScreenRect(x=0, y=0, width=640, height=480)
                runtime.update_embodiment_topology(
                    (MonitorDescriptor(id="changed", primary=True, rect=rect),),
                    rect,
                )
            return DesktopObservation(status="ok")

    runtime.windows_bridge = ChangingBridge(Path("unused"))
    args = {"grant_id": "grant-inflight", "device_id": "device-local"}
    if change == "revocation":
        with pytest.raises(OperationAuthorizationError):
            await runtime.observe_desktop(request, **args)
    else:
        result = await runtime.observe_desktop(request, **args)
        assert result.status == "stale_layout" and not result.nodes
