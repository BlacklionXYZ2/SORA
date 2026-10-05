"""P09 regressions: continuity, invalid input, delivery and authority."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.contracts.embodiment import (
    DisplayTopology,
    EmbodimentCommand,
    EmbodimentState,
    EmbodimentVerb,
    MonitorDescriptor,
    ScreenRect,
    UnityWorldPoint,
    VirtualDesktopPoint,
)
from sora.embodiment import CoordinateTransformer
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.operations import OperationAuthorizationError


def mixed() -> DisplayTopology:
    return DisplayTopology(
        virtual_desktop=ScreenRect(x=0, y=0, width=3840, height=1080),
        monitors=(
            MonitorDescriptor(
                id="a", primary=True, rect=ScreenRect(x=0, y=0, width=1920, height=1080)
            ),
            MonitorDescriptor(
                id="b", dpi_scale=1.5, rect=ScreenRect(x=1920, y=0, width=1920, height=1080)
            ),
        ),
    )


def test_mixed_dpi_continuity_and_inverse_without_hint() -> None:
    transform, topology = CoordinateTransformer(), mixed()
    before = transform.global_to_world(1919, 400, topology)
    after = transform.global_to_world(1920, 400, topology)
    assert after.x - before.x == pytest.approx(1 / 500)
    assert after.y == before.y
    for x in range(-200, 4100, 31):
        for y in (-100, 0, 500, 1079, 1200):
            world = transform.global_to_world(x, y, topology)
            assert world.x == pytest.approx(x / 500)
            assert world.y == pytest.approx(-y / 500)
            assert transform.world_to_global(world, topology) == VirtualDesktopPoint(x=x, y=y)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 0])
def test_invalid_scales_rejected(value: float) -> None:
    with pytest.raises(ValueError):
        CoordinateTransformer(value)
    with pytest.raises(ValueError):
        MonitorDescriptor(id="bad", rect=ScreenRect(x=0, y=0, width=1, height=1), dpi_scale=value)


def test_invalid_topology_and_world_rejected() -> None:
    with pytest.raises(ValueError, match="bounds"):
        DisplayTopology(
            virtual_desktop=ScreenRect(x=0, y=0, width=10, height=10), monitors=mixed().monitors
        )
    with pytest.raises(ValueError):
        UnityWorldPoint(x=float("nan"), y=0)


@pytest.mark.asyncio
async def test_dispatch_lifecycle_and_authorization(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path, identity_root=Path(__file__).resolve().parents[2] / "identity"
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        command = EmbodimentCommand(
            command_id="cmd",
            verb=EmbodimentVerb.MOVE_TO,
            target_point=VirtualDesktopPoint(x=20, y=30),
            created_at=datetime.now(UTC),
        )
        with pytest.raises(OperationAuthorizationError):
            await runtime.dispatch_embodiment_command(command)
        await persist_operation_grant(runtime, "embodiment.command", grant_id="grant-command")
        args = {"grant_id": "grant-command", "device_id": "device-local"}
        with pytest.raises(ValueError, match="no embodiment"):
            await runtime.dispatch_embodiment_command(command, **args)
        queue = runtime.register_embodiment_queue()
        with pytest.raises(ValueError, match="already connected"):
            runtime.register_embodiment_queue()
        await runtime.dispatch_embodiment_command(command, **args)
        await runtime.dispatch_embodiment_command(command, **args)
        assert queue.qsize() == 1
        for _ in range(99):
            queue.put_nowait(command)
        with pytest.raises(ValueError, match="queue is full"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(update={"command_id": "another-command"}), **args
            )
        with pytest.raises(ValueError, match="different payload"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(update={"speed_px_per_sec": 200}), **args
            )
        with pytest.raises(ValueError, match="timestamp"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(update={"created_at": datetime.now(UTC) - timedelta(minutes=1)}),
                **args,
            )
        with pytest.raises(ValueError, match="outside"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(update={"target_point": VirtualDesktopPoint(x=-100, y=0)}),
                **args,
            )
        runtime.update_embodiment_state(
            EmbodimentState(
                current_position=VirtualDesktopPoint(x=1800, y=900), containing_monitor_id="PRIMARY"
            )
        )
        runtime.update_embodiment_topology(
            (
                MonitorDescriptor(
                    id="small", primary=True, rect=ScreenRect(x=0, y=0, width=100, height=100)
                ),
            )
        )
        assert queue.empty()
        assert runtime.embodiment_state is not None
        assert runtime.embodiment_state.current_position == VirtualDesktopPoint(x=99, y=99)
        runtime.unregister_embodiment_queue(queue)
        assert not runtime.get_embodiment_projection()["connected"]
        assert runtime.embodiment_state is None
    finally:
        await runtime.close()
