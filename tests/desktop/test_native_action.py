"""Opt-in native P11.3 PRESS and P11.4 Pause acceptance on owned fixtures."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from tests.authorization_helpers import persist_operation_grant

from sora.contracts.desktop import (
    DesktopActionStatus,
    DesktopPressRequest,
    DesktopTargetRequest,
    DesktopTypeRequest,
)
from sora.contracts.models import CapabilityOperation
from sora.desktop import WindowsActionBridge, WindowsObservationBridge, WindowsTypeBridge
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


@pytest_asyncio.fixture
async def runtime(tmp_path: Path) -> AsyncIterator[SoraRuntime]:
    result = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    await result.start()
    try:
        yield result
    finally:
        await result.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SORA_TEST_UIA") != "1",
    reason="opt-in real Windows UIA action fixture",
)
async def test_real_press_is_verified_and_duplicate_contact_does_not_repeat(
    runtime: SoraRuntime, tmp_path: Path
) -> None:
    observer = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    actor = ROOT / "clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe"
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    evidence = tmp_path / "press-fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence))
    runtime.windows_bridge = WindowsObservationBridge(observer)
    runtime.windows_action_bridge = WindowsActionBridge(actor)
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    fixture_data = json.loads(evidence.read_text(encoding="utf-8"))
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    await asyncio.sleep(0.05)
        request = DesktopTargetRequest(
            process_id=process.pid,
            window_handle=fixture_data["hwnd"],
            automation_id="fixture-confirm",
            control_type="ControlType.Button",
        )
        await persist_operation_grant(
            runtime,
            request.observation_request.resource,
            grant_id="grant-native-press-observe",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        target = await runtime.acquire_desktop_target(
            request,
            grant_id="grant-native-press-observe",
            device_id="device-local",
        )
        await persist_operation_grant(
            runtime,
            f"desktop.interact:{target.target_id}:press",
            grant_id="grant-native-press",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        press = DesktopPressRequest(
            attempt_id="native-press-once",
            expected_name_after="Confirmed once",
        )
        result = await runtime.press_desktop_target(
            target.target_id,
            press,
            grant_id="grant-native-press",
            device_id="device-local",
        )
        assert result.status is DesktopActionStatus.COMPLETED
        assert result.effect_attempted and result.verified
        async with asyncio.timeout(3):
            while True:
                try:
                    fixture_data = json.loads(evidence.read_text(encoding="utf-8"))
                    if fixture_data["press_count"] == 1:
                        break
                except json.JSONDecodeError:
                    pass
                await asyncio.sleep(0.025)

        duplicate = await runtime.press_desktop_target(
            target.target_id,
            press,
            grant_id="grant-native-press",
            device_id="device-local",
        )
        assert duplicate == result
        await asyncio.sleep(0.1)
        assert json.loads(evidence.read_text(encoding="utf-8"))["press_count"] == 1
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SORA_TEST_UIA") != "1",
    reason="opt-in real Windows UIA media fixture",
)
async def test_real_pause_stops_media_clock_and_duplicate_contact_does_not_resume(
    runtime: SoraRuntime, tmp_path: Path
) -> None:
    observer = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    actor = ROOT / "clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe"
    fixture = ROOT / "clients/media_fixture/bin/Debug/net10.0-windows/media_fixture.exe"
    evidence = tmp_path / "media-fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence))
    runtime.windows_bridge = WindowsObservationBridge(observer)
    runtime.windows_action_bridge = WindowsActionBridge(actor)
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    before = json.loads(evidence.read_text(encoding="utf-8"))
                    if before["playback_state"] == "playing" and before["position_ms"] > 100:
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                await asyncio.sleep(0.05)
        await asyncio.sleep(0.2)
        advancing = json.loads(evidence.read_text(encoding="utf-8"))
        assert advancing["position_ms"] > before["position_ms"]

        request = DesktopTargetRequest(
            process_id=process.pid,
            window_handle=advancing["hwnd"],
            automation_id="media-pause",
            control_type="ControlType.Button",
        )
        await persist_operation_grant(
            runtime,
            request.observation_request.resource,
            grant_id="grant-native-media-observe",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        target = await runtime.acquire_desktop_target(
            request,
            grant_id="grant-native-media-observe",
            device_id="device-local",
        )
        await persist_operation_grant(
            runtime,
            f"desktop.interact:{target.target_id}:press",
            grant_id="grant-native-media-pause",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        press = DesktopPressRequest(
            attempt_id="native-media-pause-once",
            expected_name_after="Resume deterministic media",
        )
        result = await runtime.press_desktop_target(
            target.target_id,
            press,
            grant_id="grant-native-media-pause",
            device_id="device-local",
        )
        assert result.status is DesktopActionStatus.COMPLETED
        assert result.effect_attempted and result.verified

        async with asyncio.timeout(3):
            while True:
                try:
                    paused = json.loads(evidence.read_text(encoding="utf-8"))
                    if paused["playback_state"] == "paused" and paused["press_count"] == 1:
                        break
                except json.JSONDecodeError:
                    pass
                await asyncio.sleep(0.025)
        paused_position = paused["position_ms"]
        await asyncio.sleep(0.35)
        still_paused = json.loads(evidence.read_text(encoding="utf-8"))
        assert still_paused["playback_state"] == "paused"
        assert still_paused["position_ms"] == paused_position

        duplicate = await runtime.press_desktop_target(
            target.target_id,
            press,
            grant_id="grant-native-media-pause",
            device_id="device-local",
        )
        assert duplicate == result
        await asyncio.sleep(0.1)
        final = json.loads(evidence.read_text(encoding="utf-8"))
        assert final["playback_state"] == "paused"
        assert final["position_ms"] == paused_position
        assert final["press_count"] == 1
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("SORA_TEST_UIA") != "1",
    reason="opt-in real Windows UIA TYPE fixture",
)
async def test_real_type_sets_and_verifies_text_once(
    runtime: SoraRuntime, tmp_path: Path
) -> None:
    observer = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    typer = ROOT / "clients/windows_type/bin/Debug/net10.0-windows/windows_type.exe"
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    evidence = tmp_path / "type-fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence))
    runtime.windows_bridge = WindowsObservationBridge(observer)
    runtime.windows_type_bridge = WindowsTypeBridge(typer)
    try:
        async with asyncio.timeout(10):
            while True:
                try:
                    fixture_data = json.loads(evidence.read_text(encoding="utf-8"))
                    if fixture_data["text_value"] == "before":
                        break
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    pass
                await asyncio.sleep(0.05)
        request = DesktopTargetRequest(
            process_id=process.pid,
            window_handle=fixture_data["hwnd"],
            automation_id="fixture-text",
            control_type="ControlType.Edit",
        )
        await persist_operation_grant(
            runtime,
            request.observation_request.resource,
            grant_id="grant-native-type-observe",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        target = await runtime.acquire_desktop_target(
            request,
            grant_id="grant-native-type-observe",
            device_id="device-local",
        )
        await persist_operation_grant(
            runtime,
            f"desktop.interact:{target.target_id}:type",
            grant_id="grant-native-type",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        type_request = DesktopTypeRequest(
            attempt_id="native-type-once",
            text="SORA typed this exactly once",
        )
        result = await runtime.type_desktop_target(
            target.target_id,
            type_request,
            grant_id="grant-native-type",
            device_id="device-local",
        )
        assert result.action == "type"
        assert result.status is DesktopActionStatus.COMPLETED
        assert result.effect_attempted and result.verified
        async with asyncio.timeout(3):
            while True:
                try:
                    fixture_data = json.loads(evidence.read_text(encoding="utf-8"))
                    if fixture_data["text_value"] == type_request.text:
                        break
                except json.JSONDecodeError:
                    pass
                await asyncio.sleep(0.025)
        duplicate = await runtime.type_desktop_target(
            target.target_id,
            type_request,
            grant_id="grant-native-type",
            device_id="device-local",
        )
        assert duplicate == result
        assert json.loads(evidence.read_text(encoding="utf-8"))["text_value"] == type_request.text
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
