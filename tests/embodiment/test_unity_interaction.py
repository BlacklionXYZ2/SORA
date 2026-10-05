"""Opt-in packaged P11.4 Unity/Core/native Pause acceptance."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant
from tests.embodiment.test_unity_player import close_player_window

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.desktop import (
    DesktopActionStatus,
    DesktopPressRequest,
    DesktopTargetRequest,
    DesktopTypeRequest,
)
from sora.contracts.embodiment import EmbodimentCommand, EmbodimentVerb, VirtualDesktopPoint
from sora.contracts.models import CapabilityOperation
from sora.desktop import WindowsActionBridge, WindowsObservationBridge, WindowsTypeBridge
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("SORA_UNITY_PLAYER") or os.getenv("SORA_TEST_UIA") != "1",
    reason="opt-in packaged Unity and real Windows UIA fixtures",
)
async def test_packaged_pause_records_one_verified_embodied_interaction(
    tmp_path: Path,
) -> None:
    player = Path(os.environ["SORA_UNITY_PLAYER"]).resolve()
    observer = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    actor = ROOT / "clients/windows_action/bin/Debug/net10.0-windows/windows_action.exe"
    fixture = ROOT / "clients/media_fixture/bin/Debug/net10.0-windows/media_fixture.exe"
    assert player.is_file() and observer.is_file() and actor.is_file() and fixture.is_file()
    evidence_root = Path(os.environ.get("SORA_P11_EVIDENCE_DIR", str(tmp_path))).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    media_evidence = evidence_root / "media.json"
    interaction_evidence = evidence_root / "interaction.json"
    player_log = evidence_root / "player.log"
    for path in (
        media_evidence,
        interaction_evidence,
        player_log,
        evidence_root / "acceptance.json",
    ):
        path.unlink(missing_ok=True)
    media: asyncio.subprocess.Process | None = None
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    runtime.windows_bridge = WindowsObservationBridge(observer)
    runtime.windows_action_bridge = WindowsActionBridge(actor)
    await runtime.start()
    token = secrets.token_urlsafe(32)
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token=token))
    unity: asyncio.subprocess.Process | None = None
    try:
        for action in ("connect", "topology"):
            await persist_operation_grant(
                runtime, f"embodiment.{action}", grant_id=f"fixture-{action}"
            )
        await server.start()
        env = dict(
            os.environ,
            SORA_API_TOKEN=token,
            SORA_CORE_PORT=str(server.actual_port),
            SORA_EMBODIMENT_CONNECT_GRANT="fixture-connect",
            SORA_EMBODIMENT_TOPOLOGY_GRANT="fixture-topology",
            SORA_EMBODIMENT_DEVICE_ID="device-local",
            SORA_INTERACTION_EVIDENCE_PATH=str(interaction_evidence),
        )
        env.pop("SORA_VRM_PATH", None)
        unity = await asyncio.create_subprocess_exec(
            str(player), "-logFile", str(player_log), env=env
        )

        async with asyncio.timeout(45):
            while runtime.embodiment_state is None or not runtime.embodiment_state.visible:
                if unity.returncode is not None:
                    raise AssertionError(f"Unity exited {unity.returncode}")
                await asyncio.sleep(0.1)
        topology = runtime.topology_manager.topology
        target_monitor = next(monitor for monitor in topology.monitors if monitor.primary)
        fixture_arguments = [str(fixture), str(media_evidence)]
        require_secondary = os.getenv("SORA_P11_REQUIRE_SECONDARY") == "1"
        if require_secondary:
            secondary = next(
                (monitor for monitor in topology.monitors if not monitor.primary),
                None,
            )
            assert secondary is not None, "P15.4 requires an attached secondary monitor"
            target_monitor = secondary
            area = secondary.work_area or secondary.rect
            fixture_arguments.extend((str(area.x + 80), str(area.y + 80)))
        media = await asyncio.create_subprocess_exec(*fixture_arguments)
        async with asyncio.timeout(10):
            while True:
                try:
                    media_before = json.loads(media_evidence.read_text(encoding="utf-8"))
                    if (
                        media_before["playback_state"] == "playing"
                        and media_before["position_ms"] > 100
                    ):
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                await asyncio.sleep(0.05)

        preposition: VirtualDesktopPoint | None = None
        settled_preposition: VirtualDesktopPoint | None = None
        if require_secondary:
            button_before = media_before["button"]
            target_x = button_before["x"] + button_before["width"] // 2
            preposition = VirtualDesktopPoint(
                x=max(area.x + 40, target_x - 300),
                y=area.bottom - 100,
            )
            await persist_operation_grant(
                runtime, "embodiment.command", grant_id="fixture-command"
            )
            await runtime.dispatch_embodiment_command(
                EmbodimentCommand(
                    command_id="p15-secondary-preposition",
                    verb=EmbodimentVerb.MOVE_TO,
                    target_point=preposition,
                    topology_revision=runtime.topology_manager.revision,
                    created_at=datetime.now(UTC),
                    speed_px_per_sec=3000,
                ),
                grant_id="fixture-command",
                device_id="device-local",
            )
            try:
                async with asyncio.timeout(20):
                    while (
                        runtime.embodiment_state is None
                        or runtime.embodiment_state.presentation_state != "idle"
                        or runtime.embodiment_state.containing_monitor_id != target_monitor.id
                        or runtime.embodiment_state.current_position.x >= target_x
                    ):
                        await asyncio.sleep(0.05)
                assert runtime.embodiment_state is not None
                settled_preposition = runtime.embodiment_state.current_position
            except TimeoutError as exc:
                state = runtime.embodiment_state
                detail = state.model_dump_json() if state is not None else "disconnected"
                raise AssertionError(f"secondary preposition did not settle: {detail}") from exc

        target_request = DesktopTargetRequest(
            process_id=media.pid,
            window_handle=media_before["hwnd"],
            automation_id="media-pause",
            control_type="ControlType.Button",
        )
        await persist_operation_grant(
            runtime,
            target_request.observation_request.resource,
            grant_id="grant-pause-observe",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        target = await runtime.acquire_desktop_target(
            target_request,
            grant_id="grant-pause-observe",
            device_id="device-local",
        )
        await persist_operation_grant(
            runtime,
            f"desktop.interact:{target.target_id}:press",
            grant_id="grant-pause-interact",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        request = DesktopPressRequest(
            attempt_id="packaged-pause-once",
            expected_name_after="Resume deterministic media",
        )
        command = await runtime.prepare_desktop_press_interaction(
            target.target_id,
            request,
            grant_id="grant-pause-interact",
            device_id="device-local",
        )
        assert "grant-pause-interact" not in command.model_dump_json()

        async with asyncio.timeout(30):
            while True:
                try:
                    recorded = json.loads(interaction_evidence.read_text(encoding="utf-8"))
                    events = recorded["events"]
                    if events and events[-1]["phase"] in {
                        "completed",
                        "failed",
                        "unknownoutcome",
                    }:
                        break
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    pass
                await asyncio.sleep(0.05)
        phases = [event["phase"] for event in events]
        assert phases == [
            "target_selected",
            "navigate",
            "align",
            "reach",
            "contact",
            "invoke",
            "verify",
            "retract",
            "completed",
        ]
        terminal = events[-1]
        assert terminal["reason"] == "completed"
        assert terminal["effect_attempted"] is True
        assert terminal["verified"] is True
        assert "grant-pause-interact" not in interaction_evidence.read_text(encoding="utf-8")

        paused = json.loads(media_evidence.read_text(encoding="utf-8"))
        assert paused["playback_state"] == "paused" and paused["press_count"] == 1
        paused_position = paused["position_ms"]
        await asyncio.sleep(0.35)
        still_paused = json.loads(media_evidence.read_text(encoding="utf-8"))
        assert still_paused["position_ms"] == paused_position
        button = still_paused["button"]
        button_x = button["x"] + button["width"] // 2
        button_y = button["y"] + button["height"] // 2
        monitor_rect = target_monitor.rect
        assert monitor_rect.x <= button_x < monitor_rect.x + monitor_rect.width
        assert monitor_rect.y <= button_y < monitor_rect.y + monitor_rect.height
        if require_secondary:
            assert target_monitor.primary is False
        journaled = await runtime.press_desktop_target(
            target.target_id,
            request,
            grant_id="grant-pause-interact",
            device_id="device-local",
        )
        assert journaled.status is DesktopActionStatus.COMPLETED and journaled.verified
        assert json.loads(media_evidence.read_text(encoding="utf-8"))["press_count"] == 1
        recorded_at = datetime.fromisoformat(terminal["recorded_at"].replace("Z", "+00:00"))
        assert recorded_at <= datetime.now(UTC)
        (evidence_root / "acceptance.json").write_text(
            json.dumps(
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "action": "press",
                    "semantic_intent": "pause deterministic media",
                    "attempt_id": request.attempt_id,
                    "phases": phases,
                    "terminal": {
                        "status": journaled.status.value,
                        "reason": journaled.reason,
                        "effect_attempted": journaled.effect_attempted,
                        "verified": journaled.verified,
                    },
                    "playback": {
                        "before": media_before["playback_state"],
                        "after": still_paused["playback_state"],
                        "position_stopped": still_paused["position_ms"] == paused_position,
                        "press_count": still_paused["press_count"],
                    },
                    "grant_serialized_to_unity_or_evidence": False,
                    "duplicate_effect_count": 0,
                    "target_monitor": {
                        "id": target_monitor.id,
                        "primary": target_monitor.primary,
                        "rect": target_monitor.rect.model_dump(mode="json"),
                        "button_center": {"x": button_x, "y": button_y},
                    },
                    "secondary_preposition": (
                        {
                            "requested": preposition.model_dump(mode="json"),
                            "settled": settled_preposition.model_dump(mode="json"),
                        }
                        if preposition is not None and settled_preposition is not None
                        else None
                    ),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        if unity is not None and unity.returncode is None:
            close_player_window(unity.pid)
            try:
                await asyncio.wait_for(unity.wait(), 10)
            except TimeoutError:
                unity.kill()
                await unity.wait()
        if media is not None:
            if media.returncode is None:
                media.kill()
            await media.wait()
        await server.close()
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("SORA_UNITY_PLAYER") or os.getenv("SORA_TEST_UIA") != "1",
    reason="opt-in packaged Unity and real Windows UIA fixtures",
)
async def test_packaged_type_records_verified_text_postcondition(tmp_path: Path) -> None:
    player = Path(os.environ["SORA_UNITY_PLAYER"]).resolve()
    observer = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    typer = ROOT / "clients/windows_type/bin/Debug/net10.0-windows/windows_type.exe"
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    assert player.is_file() and observer.is_file() and typer.is_file() and fixture.is_file()
    evidence_root = Path(os.environ.get("SORA_P11_TYPE_EVIDENCE_DIR", str(tmp_path))).resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    fixture_evidence = evidence_root / "type-fixture.json"
    interaction_evidence = evidence_root / "interaction.json"
    player_log = evidence_root / "player.log"
    for path in (
        fixture_evidence,
        interaction_evidence,
        player_log,
        evidence_root / "acceptance.json",
    ):
        path.unlink(missing_ok=True)
    fixture_process = await asyncio.create_subprocess_exec(str(fixture), str(fixture_evidence))
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=ROOT / "identity"),
        provider=DeterministicProvider(),
    )
    runtime.windows_bridge = WindowsObservationBridge(observer)
    runtime.windows_type_bridge = WindowsTypeBridge(typer)
    await runtime.start()
    token = secrets.token_urlsafe(32)
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token=token))
    unity: asyncio.subprocess.Process | None = None
    try:
        for action in ("connect", "topology"):
            await persist_operation_grant(
                runtime, f"embodiment.{action}", grant_id=f"type-fixture-{action}"
            )
        await server.start()
        env = dict(
            os.environ,
            SORA_API_TOKEN=token,
            SORA_CORE_PORT=str(server.actual_port),
            SORA_EMBODIMENT_CONNECT_GRANT="type-fixture-connect",
            SORA_EMBODIMENT_TOPOLOGY_GRANT="type-fixture-topology",
            SORA_EMBODIMENT_DEVICE_ID="device-local",
            SORA_INTERACTION_EVIDENCE_PATH=str(interaction_evidence),
        )
        env.pop("SORA_VRM_PATH", None)
        unity = await asyncio.create_subprocess_exec(
            str(player), "-logFile", str(player_log), env=env
        )
        async with asyncio.timeout(45):
            while runtime.embodiment_state is None or not runtime.embodiment_state.visible:
                if unity.returncode is not None:
                    raise AssertionError(f"Unity exited {unity.returncode}")
                await asyncio.sleep(0.1)
        async with asyncio.timeout(10):
            while True:
                try:
                    fixture_before = json.loads(fixture_evidence.read_text(encoding="utf-8"))
                    if fixture_before["text_value"] == "before":
                        break
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    pass
                await asyncio.sleep(0.05)

        target_request = DesktopTargetRequest(
            process_id=fixture_process.pid,
            window_handle=fixture_before["hwnd"],
            automation_id="fixture-text",
            control_type="ControlType.Edit",
        )
        await persist_operation_grant(
            runtime,
            target_request.observation_request.resource,
            grant_id="grant-type-observe",
            operation=CapabilityOperation.DESKTOP_OBSERVE,
        )
        target = await runtime.acquire_desktop_target(
            target_request,
            grant_id="grant-type-observe",
            device_id="device-local",
        )
        await persist_operation_grant(
            runtime,
            f"desktop.interact:{target.target_id}:type",
            grant_id="grant-type-interact",
            operation=CapabilityOperation.DESKTOP_INTERACT,
        )
        request = DesktopTypeRequest(
            attempt_id="packaged-type-once",
            text="SORA logical TYPE verified",
        )
        command = await runtime.prepare_desktop_type_interaction(
            target.target_id,
            request,
            grant_id="grant-type-interact",
            device_id="device-local",
        )
        serialized = command.model_dump_json()
        assert request.text not in serialized and "grant-type-interact" not in serialized
        async with asyncio.timeout(30):
            while True:
                try:
                    recorded = json.loads(interaction_evidence.read_text(encoding="utf-8"))
                    events = recorded["events"]
                    if events and events[-1]["phase"] in {
                        "completed",
                        "failed",
                        "unknownoutcome",
                    }:
                        break
                except (FileNotFoundError, json.JSONDecodeError, KeyError):
                    pass
                await asyncio.sleep(0.05)
        phases = [event["phase"] for event in events]
        assert phases == [
            "target_selected",
            "navigate",
            "align",
            "reach",
            "contact",
            "invoke",
            "verify",
            "retract",
            "completed",
        ]
        terminal = events[-1]
        assert terminal["reason"] == "completed"
        assert terminal["effect_attempted"] is True and terminal["verified"] is True
        evidence_text = interaction_evidence.read_text(encoding="utf-8")
        assert request.text not in evidence_text and "grant-type-interact" not in evidence_text
        fixture_after = json.loads(fixture_evidence.read_text(encoding="utf-8"))
        assert fixture_after["text_value"] == request.text
        assert fixture_after["text_change_count"] > fixture_before["text_change_count"]
        change_count_after_effect = fixture_after["text_change_count"]
        journaled = await runtime.type_desktop_target(
            target.target_id,
            request,
            grant_id="grant-type-interact",
            device_id="device-local",
        )
        assert journaled.status is DesktopActionStatus.COMPLETED and journaled.verified
        after_duplicate = json.loads(fixture_evidence.read_text(encoding="utf-8"))
        assert after_duplicate["text_change_count"] == change_count_after_effect
        (evidence_root / "acceptance.json").write_text(
            json.dumps(
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "action": "type",
                    "attempt_id": request.attempt_id,
                    "phases": phases,
                    "terminal": {
                        "status": journaled.status.value,
                        "reason": journaled.reason,
                        "effect_attempted": journaled.effect_attempted,
                        "verified": journaled.verified,
                    },
                    "text_postcondition_verified": fixture_after["text_value"] == request.text,
                    "text_change_event_delta": (
                        fixture_after["text_change_count"] - fixture_before["text_change_count"]
                    ),
                    "text_or_grant_serialized_to_unity_evidence": False,
                    "duplicate_effect_count": 0,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    finally:
        if unity is not None and unity.returncode is None:
            close_player_window(unity.pid)
            try:
                await asyncio.wait_for(unity.wait(), 10)
            except TimeoutError:
                unity.kill()
                await unity.wait()
        if fixture_process.returncode is None:
            fixture_process.kill()
        await fixture_process.wait()
        await server.close()
        await runtime.close()
