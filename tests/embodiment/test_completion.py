"""P09 work-area and presentation-only hook regressions."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.contracts.embodiment import (
    EmbodimentCommand,
    EmbodimentPresentationState,
    EmbodimentState,
    EmbodimentVerb,
    MonitorDescriptor,
    ScreenRect,
    VirtualDesktopPoint,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError


@pytest.mark.parametrize(
    "work", [(0, 40, 1920, 1040), (0, 0, 1920, 1040), (40, 0, 1880, 1080), (0, 0, 1880, 1080)]
)
def test_taskbar_work_areas_roundtrip(work: tuple[int, int, int, int]) -> None:
    x, y, width, height = work
    monitor = MonitorDescriptor(
        id="primary",
        primary=True,
        rect=ScreenRect(x=0, y=0, width=1920, height=1080),
        work_area=ScreenRect(x=x, y=y, width=width, height=height),
        dpi_scale=1.5,
    )
    assert MonitorDescriptor.model_validate_json(monitor.model_dump_json()) == monitor
    with pytest.raises(ValueError, match="work_area"):
        MonitorDescriptor(
            id="bad",
            rect=ScreenRect(x=0, y=0, width=100, height=100),
            work_area=ScreenRect(x=-1, y=0, width=100, height=100),
        )


def test_phase_requires_semantic_identity_and_marker_is_bounded() -> None:
    with pytest.raises(ValueError, match="semantic_action_id"):
        EmbodimentCommand(
            command_id="phase", verb=EmbodimentVerb.PRESENTATION_PHASE, created_at=datetime.now(UTC)
        )
    with pytest.raises(ValueError):
        EmbodimentCommand(
            command_id="marker",
            verb=EmbodimentVerb.SHOW_MARKER,
            target_point=VirtualDesktopPoint(x=10, y=10),
            marker_duration_seconds=31,
            created_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_marker_requires_authority_and_stays_on_one_display(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity"
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        command = EmbodimentCommand(
            command_id="marker",
            verb=EmbodimentVerb.SHOW_MARKER,
            target_point=VirtualDesktopPoint(x=10, y=10),
            target_id="fixture-target",
            target_rect=ScreenRect(x=5, y=5, width=20, height=20),
            created_at=datetime.now(UTC),
        )
        queue = runtime.register_embodiment_queue()
        with pytest.raises(OperationAuthorizationError):
            await runtime.dispatch_embodiment_command(command)
        gesture = EmbodimentCommand(
            command_id="gesture-wave",
            verb=EmbodimentVerb.SET_STATE,
            state=EmbodimentPresentationState.WAVING,
            created_at=datetime.now(UTC),
        )
        with pytest.raises(OperationAuthorizationError):
            await runtime.dispatch_embodiment_command(gesture)
        await persist_operation_grant(runtime, "embodiment.command", grant_id="grant-marker")
        args = {"grant_id": "grant-marker", "device_id": "device-local"}
        await runtime.dispatch_embodiment_command(gesture, **args)
        assert queue.get_nowait().state is EmbodimentPresentationState.WAVING
        await runtime.dispatch_embodiment_command(command, **args)
        assert queue.get_nowait().target_id == "fixture-target"
        with pytest.raises(ValueError, match="rectangle"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(
                    update={
                        "command_id": "bad-rect",
                        "target_rect": ScreenRect(x=0, y=0, width=2000, height=1080),
                    }
                ),
                **args,
            )
        phase = EmbodimentCommand(
            command_id="phase",
            verb=EmbodimentVerb.PRESENTATION_PHASE,
            semantic_action_id="fixture-action",
            semantic_phase="contact",
            created_at=datetime.now(UTC),
        )
        await runtime.dispatch_embodiment_command(phase, **args)
        assert queue.get_nowait().semantic_phase == "contact"
        # Queuing a phase is presentation only and does not establish any execution result.
        assert runtime.embodiment_state is None
        runtime.update_embodiment_state(
            EmbodimentState(
                current_position=VirtualDesktopPoint(x=50, y=50),
                containing_monitor_id="PRIMARY",
                interpreted_target_id="fixture-target",
                marker_position=VirtualDesktopPoint(x=10, y=10),
            )
        )
        with pytest.raises(ValueError, match="marker position"):
            runtime.update_embodiment_state(
                EmbodimentState(
                    current_position=VirtualDesktopPoint(x=50, y=50),
                    containing_monitor_id="PRIMARY",
                    marker_position=VirtualDesktopPoint(x=-100, y=-100),
                )
            )
        runtime.update_embodiment_topology(
            (
                MonitorDescriptor(
                    id="new", primary=True, rect=ScreenRect(x=0, y=0, width=800, height=600)
                ),
            )
        )
        assert runtime.embodiment_state is not None
        assert runtime.embodiment_state.marker_position is None
        assert runtime.embodiment_state.interpreted_target_id is None
    finally:
        await runtime.close()
