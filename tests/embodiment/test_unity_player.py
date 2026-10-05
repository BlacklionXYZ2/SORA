"""Opt-in packaged Unity/Core acceptance; launches only the supplied local test player."""

from __future__ import annotations

import asyncio
import ctypes
import json
import os
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant
from tests.embodiment.native_input_probe import probe_input

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.desktop_objects import (
    DesktopObjectAffordance,
    DesktopObjectAffordanceRequest,
)
from sora.contracts.embodiment import (
    EmbodimentCommand,
    EmbodimentFeedbackEvent,
    EmbodimentState,
    EmbodimentVerb,
    ScreenRect,
    VirtualDesktopPoint,
)
from sora.contracts.models import (
    CapabilityOperation,
    DesktopObjectRecord,
    DesktopObjectVisibility,
)
from sora.desktop_objects import DesktopObjectDefinition
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime


def close_player_window(pid: int) -> None:
    """WM_CLOSE only windows belonging to the child we launched."""
    user32 = ctypes.windll.user32
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(window: int, _: int) -> bool:
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(window), ctypes.byref(owner))
        if owner.value == pid:
            user32.PostMessageW(ctypes.c_void_p(window), 0x0010, 0, 0)
        return True

    wrapped = callback_type(callback)
    user32.EnumWindows(wrapped, 0)


@pytest.mark.asyncio
@pytest.mark.skipif(not os.environ.get("SORA_UNITY_PLAYER"), reason="opt-in packaged Unity player")
async def test_packaged_unity_core_acceptance(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    player = Path(os.environ["SORA_UNITY_PLAYER"]).resolve()
    assert player.is_file()
    evidence = root / ".local/p09-unity-evidence/player"
    evidence.mkdir(parents=True, exist_ok=True)
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=root / "identity"),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = secrets.token_urlsafe(32)
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token=token))
    process: asyncio.subprocess.Process | None = None

    async def wait_state(
        predicate: Callable[[EmbodimentState], bool], timeout: float = 45
    ) -> EmbodimentState:
        async with asyncio.timeout(timeout):
            while True:
                state = runtime.embodiment_state
                if state is not None and predicate(state):
                    return state
                if process is not None and process.returncode is not None:
                    raise AssertionError(f"Unity exited {process.returncode}; inspect player.log")
                await asyncio.sleep(0.1)

    async def command(
        verb: EmbodimentVerb, point: VirtualDesktopPoint | None = None, **extra: object
    ) -> None:
        payload = {
            "command_id": secrets.token_hex(12),
            "verb": verb,
            "target_point": point,
            "topology_revision": runtime.topology_manager.revision,
            "created_at": datetime.now(UTC),
            "speed_px_per_sec": 3000.0,
            **extra,
        }
        await runtime.dispatch_embodiment_command(
            EmbodimentCommand.model_validate(payload),
            grant_id="fixture-command",
            device_id="device-local",
        )

    async def launch(
        label: str,
        *,
        ragdoll_evidence: Path | None = None,
        support_evidence: Path | None = None,
    ) -> asyncio.subprocess.Process:
        destination = evidence / label
        destination.mkdir(exist_ok=True)
        for name in ("presentation-metrics.json", "camera.png"):
            (destination / name).unlink(missing_ok=True)
        env = dict(
            os.environ,
            SORA_API_TOKEN=token,
            SORA_CORE_PORT=str(server.actual_port),
            SORA_EMBODIMENT_CONNECT_GRANT="fixture-connect",
            SORA_EMBODIMENT_TOPOLOGY_GRANT="fixture-topology",
            SORA_EMBODIMENT_DEVICE_ID="device-local",
            SORA_PRESENTATION_EVIDENCE_DIR=str(destination),
        )
        env.pop("SORA_VRM_PATH", None)
        env.pop("SORA_DEBUG_OVERLAY", None)
        env.pop("SORA_RAGDOLL_EVIDENCE_PATH", None)
        env.pop("SORA_SUPPORT_EVIDENCE_PATH", None)
        interaction_evidence = destination / "interaction-evidence.json"
        interaction_evidence.unlink(missing_ok=True)
        env["SORA_INTERACTION_EVIDENCE_PATH"] = str(interaction_evidence)
        if ragdoll_evidence is not None:
            ragdoll_evidence.unlink(missing_ok=True)
            env["SORA_RAGDOLL_EVIDENCE_PATH"] = str(ragdoll_evidence)
        if support_evidence is not None:
            support_evidence.unlink(missing_ok=True)
            env["SORA_SUPPORT_EVIDENCE_PATH"] = str(support_evidence)
        child = await asyncio.create_subprocess_exec(
            str(player), "-logFile", str(destination / "player.log"), env=env
        )
        print(f"Unity fixture {label} PID={child.pid}", flush=True)
        return child

    try:
        for action in ("connect", "command", "topology"):
            await persist_operation_grant(
                runtime, f"embodiment.{action}", grant_id=f"fixture-{action}"
            )
        await server.start()
        process = await launch("first")
        initial = await wait_state(lambda s: s.visible)
        topology = runtime.topology_manager.topology
        primary = next(m for m in topology.monitors if m.primary)
        area = primary.work_area or primary.rect
        object_rect = ScreenRect(
            x=area.x + area.width // 2 - 120,
            y=area.y + area.height // 2 - 80,
            width=240,
            height=160,
        )
        runtime.register_desktop_object(
            DesktopObjectDefinition(
                record=DesktopObjectRecord(
                    object_id="object:packaged-fixture",
                    object_type="fixture_card",
                    owner_id=runtime.config.owner_id,
                    anchor="packaged_fixture",
                    visibility=DesktopObjectVisibility.LOCAL_ONLY,
                    affordances=("look", "point", "touch"),
                    canonical_ref="task:packaged-fixture",
                    version=1,
                ),
                label="Packaged fixture card",
                rect=object_rect,
                topology_revision=runtime.topology_manager.revision,
                content={"summary": "bounded packaged fixture", "state": "unchanged"},
            )
        )
        object_projection = runtime.project_desktop_objects()
        assert len(object_projection) == 1
        assert object_projection[0].affordances == tuple(DesktopObjectAffordance)
        for affordance, operation in (
            (DesktopObjectAffordance.LOOK, CapabilityOperation.DESKTOP_PRESENT),
            (DesktopObjectAffordance.POINT, CapabilityOperation.DESKTOP_PRESENT),
            (DesktopObjectAffordance.TOUCH, CapabilityOperation.DESKTOP_INTERACT),
        ):
            await persist_operation_grant(
                runtime,
                f"desktop.object:object:packaged-fixture:{affordance.value}",
                grant_id=f"fixture-object-{affordance.value}",
                operation=operation,
            )
        object_commands: dict[str, str] = {}
        for affordance in DesktopObjectAffordance:
            request_id = f"packaged-object-{affordance.value}"
            object_command = await runtime.present_desktop_object_affordance(
                DesktopObjectAffordanceRequest(
                    request_id=request_id,
                    object_id="object:packaged-fixture",
                    affordance=affordance,
                    expected_version=1,
                ),
                grant_id=f"fixture-object-{affordance.value}",
                device_id="device-local",
            )
            object_commands[affordance.value] = object_command.command_id
            if affordance is DesktopObjectAffordance.LOOK:
                await wait_state(lambda state: state.presentation_state == "looking")
            elif affordance is DesktopObjectAffordance.POINT:
                await wait_state(
                    lambda state: state.interpreted_target_id == "object:packaged-fixture"
                )
            else:
                terminal: EmbodimentFeedbackEvent | None = None
                async with asyncio.timeout(20):
                    while terminal is None:
                        terminal = next(
                            (
                                event
                                for event in runtime.embodiment_feedback
                                if event.kind.value in {"completed", "failed"}
                                and event.correlation_id == request_id
                            ),
                            None,
                        )
                        if terminal is not None:
                            break
                        await asyncio.sleep(0.1)
                assert terminal.kind.value == "completed", terminal.detail
        object_snapshot = runtime.desktop_object_affordances.snapshot(
            "object:packaged-fixture"
        )
        assert object_snapshot is not None
        assert object_snapshot.record.version == 1
        right = VirtualDesktopPoint(x=area.x + area.width * 2 // 3, y=area.bottom - 100)
        left = VirtualDesktopPoint(x=area.x + area.width // 3, y=area.bottom - 100)
        await command(EmbodimentVerb.MOVE_TO, right)
        await wait_state(lambda s: s.current_position == right and s.presentation_state == "idle")
        await command(EmbodimentVerb.MOVE_TO, left)
        await wait_state(lambda s: s.current_position == left and s.presentation_state == "idle")
        secondary = next((m for m in topology.monitors if not m.primary), None)
        if secondary is not None:
            work = secondary.work_area or secondary.rect
            secondary_point = VirtualDesktopPoint(x=work.x + work.width // 2, y=work.bottom - 100)
            await command(EmbodimentVerb.MOVE_TO, secondary_point)
            await wait_state(
                lambda s: s.current_position == secondary_point and s.presentation_state == "idle"
            )
            await command(EmbodimentVerb.MOVE_TO, left)
            await wait_state(
                lambda s: s.current_position == left and s.presentation_state == "idle"
            )
        await command(EmbodimentVerb.LOOK_AT, right)
        await wait_state(lambda s: s.presentation_state == "looking")
        await command(
            EmbodimentVerb.SHOW_MARKER,
            right,
            target_id="fixture-target",
            marker_duration_seconds=12.0,
        )
        await wait_state(
            lambda s: s.interpreted_target_id == "fixture-target" and s.marker_position == right
        )
        await wait_state(lambda s: s.marker_position is None, timeout=15)
        await command(EmbodimentVerb.SET_STATE, state="idle")
        await wait_state(lambda s: s.presentation_state == "idle")
        cross_process_input_tested = os.getenv("SORA_SKIP_NATIVE_INPUT_PROBE") != "1"
        landed: EmbodimentState | None = None
        if cross_process_input_tested:
            await probe_input(process.pid, left.x, left.y, root, evidence)
            dragged = await wait_state(
                lambda s: s.current_position.x >= left.x + 75 and
                topology.is_point_on_display(s.current_position.x, s.current_position.y),
                timeout=10,
            )
            assert dragged.current_position != left
            landed = await wait_state(
                lambda s: s.current_position.y == area.bottom - 1 and
                topology.is_point_on_display(s.current_position.x, s.current_position.y),
                timeout=10,
            )
            assert landed.current_position.y == area.bottom - 1
            async with asyncio.timeout(5):
                while not {
                    "grabbed",
                    "released",
                    "clicked",
                    "poked",
                    "fell",
                    "landed",
                }.issubset({event.kind.value for event in runtime.embodiment_feedback}):
                    await asyncio.sleep(0.1)
        await command(EmbodimentVerb.MOVE_TO, left)
        await wait_state(
            lambda s: s.current_position == left and s.presentation_state == "idle"
        )
        # Collect a bounded warmup-excluded idle/performance window. No provider calls are made.
        async with asyncio.timeout(90):
            while not (evidence / "first/presentation-metrics.json").exists():
                await asyncio.sleep(0.5)
        close_player_window(process.pid)
        await asyncio.wait_for(process.wait(), 15)
        assert process.returncode == 0
        metrics = json.loads(
            (evidence / "first/presentation-metrics.json").read_text(encoding="utf-8")
        )
        desktop = topology.virtual_desktop
        assert metrics["viewport"] == {"width": desktop.width, "height": desktop.height}
        assert abs(metrics["rendered_client_anchor"]["x"] - (left.x - desktop.x)) <= 1
        assert abs(metrics["rendered_client_anchor"]["y"] - (left.y - desktop.y)) <= 1
        async with asyncio.timeout(5):
            while runtime.get_embodiment_projection()["connected"]:
                await asyncio.sleep(0.1)
        assert server.is_serving and runtime.embodiment_state is None
        process = await launch("reconnect")
        reconnected = await wait_state(lambda s: s.visible)
        await asyncio.sleep(2)
        assert runtime.embodiment_state is not None
        assert runtime.embodiment_state.presentation_state == "idle"
        assert runtime.embodiment_state.current_position == reconnected.current_position
        assert reconnected.current_position != left
        close_player_window(process.pid)
        await asyncio.wait_for(process.wait(), 15)
        assert process.returncode == 0 and server.is_serving
        recovery_path = evidence / "recovery/ragdoll-recovery.json"
        process = await launch("recovery", ragdoll_evidence=recovery_path)
        await wait_state(lambda s: s.visible)
        async with asyncio.timeout(15):
            while not recovery_path.exists():
                if process.returncode is not None:
                    raise AssertionError(
                        f"Unity exited {process.returncode}; inspect recovery/player.log"
                    )
                await asyncio.sleep(0.1)
        recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
        assert recovery["constrained_joint_count"] >= 11
        assert recovery["body_collision_enabled"] is True
        assert recovery["pose_lease_released"] is True
        assert [item["requested"] for item in recovery["scenarios"]] == [
            "Front", "Back", "LeftSide", "RightSide"
        ]
        assert all(
            item["requested"] == item["detected"] and item["outcome"] == "Recovered"
            for item in recovery["scenarios"]
        )
        close_player_window(process.pid)
        await asyncio.wait_for(process.wait(), 15)
        assert process.returncode == 0 and server.is_serving
        async with asyncio.timeout(5):
            while runtime.get_embodiment_projection()["connected"]:
                await asyncio.sleep(0.1)
        support_path = evidence / "surfaces/support-surfaces.json"
        process = await launch("surfaces", support_evidence=support_path)
        await wait_state(lambda s: s.visible)
        observed = datetime.now(UTC)
        await command(
            EmbodimentVerb.SET_SUPPORTS,
            support_surfaces=[
                {
                    "surface_id": "window:core-fixture",
                    "kind": "window_top",
                    "rect": {
                        "x": area.x + area.width // 2 - 250,
                        "y": area.bottom - 180,
                        "width": 500,
                        "height": 120,
                    },
                    "state": "active",
                    "observed_at": observed,
                    "expires_at": observed + timedelta(seconds=10),
                }
            ],
        )
        async with asyncio.timeout(25):
            while not support_path.exists():
                if process.returncode is not None:
                    raise AssertionError(
                        f"Unity exited {process.returncode}; inspect surfaces/player.log"
                    )
                await asyncio.sleep(0.1)
        surfaces = json.loads(support_path.read_text(encoding="utf-8"))
        assert surfaces["core_snapshot_received"] is True
        assert surfaces["moving_surface_carried_avatar"] is True
        assert [item["invalidation"] for item in surfaces["scenarios"]] == [
            "Minimized", "Closed", "Occluded"
        ]
        assert all(
            item["landed_on"] == "window_top"
            and item["final_support"] == "taskbar"
            and item["resumed_falling"] is True
            for item in surfaces["scenarios"]
        )
        async with asyncio.timeout(5):
            while "support_removed" not in {
                event.kind.value for event in runtime.embodiment_feedback
            }:
                await asyncio.sleep(0.1)
        close_player_window(process.pid)
        await asyncio.wait_for(process.wait(), 15)
        assert process.returncode == 0 and server.is_serving
        spring_joint_counts: dict[str, int] = {}
        for label in ("first", "reconnect", "recovery", "surfaces"):
            player_log = (evidence / label / "player.log").read_text(encoding="utf-8")
            assert "Exception" not in player_log
            assert "Leak Detected" not in player_log
            tuned = re.search(r"Secondary motion tuned: (\d+) spring joints", player_log)
            assert tuned is not None and int(tuned.group(1)) > 0
            spring_joint_counts[label] = int(tuned.group(1))
        (evidence / "acceptance.json").write_text(
            json.dumps(
                {
                    "recorded_at": datetime.now(UTC).isoformat(),
                    "player": str(player),
                    "topology": topology.model_dump(mode="json"),
                    "initial_state": initial.model_dump(mode="json"),
                    "checks": [
                        "VRM visible",
                        "native topology",
                        "right/left arrival",
                        "gaze state",
                        "marker identity/expiry",
                        "idle reset",
                        "runtime SpringBone tuning",
                        "front/back/left/right ragdoll recovery",
                        "exclusive pose lease released",
                        "bounded constrained-joint recovery",
                        "Core-delivered bounded window support snapshot",
                        "moving/minimized/closed/occluded support lifecycle",
                        "debounced physical feedback received by Core",
                        "scoped desktop object look/point/touch lifecycle",
                        "desktop object canonical state unchanged",
                        "graceful close",
                        "Core survives",
                        "reconnect without movement replay",
                    ] + ([
                        "native blank/avatar input routing",
                        "avatar drag reported and anchor restored",
                        "simple gravity landing",
                    ] if cross_process_input_tested else []),
                    "hardware_transitions_tested": False,
                    "cross_process_input_tested": cross_process_input_tested,
                    "secondary_monitor_movement_tested": secondary is not None,
                    "simple_physics": (
                        {
                            "status": "passed",
                            "vertical_lift_px": 160,
                            "landing_position": landed.current_position.model_dump(mode="json"),
                            "support_y": area.bottom - 1,
                            "anchor_restored": True,
                            "spring_joint_counts": spring_joint_counts,
                        }
                        if landed is not None
                        else {
                            "status": "not_run",
                            "reason": "native input probe explicitly skipped by the caller",
                            "spring_joint_counts": spring_joint_counts,
                        }
                    ),
                    "ragdoll_recovery": recovery,
                    "support_surfaces": surfaces,
                    "physics_feedback": {
                        "kinds": sorted(
                            {event.kind.value for event in runtime.embodiment_feedback}
                        ),
                        "event_count": len(runtime.embodiment_feedback),
                        "projection_count": len(
                            runtime.get_embodiment_projection()["recent_feedback"]
                        ),
                    },
                    "desktop_object_affordance": {
                        "object_id": "object:packaged-fixture",
                        "commands": object_commands,
                        "projected_affordances": [
                            value.value for value in object_projection[0].affordances
                        ],
                        "completed_touch": any(
                            event.kind.value == "completed"
                            and event.correlation_id == "packaged-object-touch"
                            for event in runtime.embodiment_feedback
                        ),
                        "canonical_version": object_snapshot.record.version,
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    finally:
        if process is not None and process.returncode is None:
            close_player_window(process.pid)
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()
        await server.close()
        await runtime.close()
