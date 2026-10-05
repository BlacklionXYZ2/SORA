"""Deterministic multi-monitor coordinate transformation engine."""

from __future__ import annotations

import math

from sora.contracts.embodiment import (
    DisplayTopology,
    MonitorDescriptor,
    MonitorLocalPoint,
    UnityWorldPoint,
    VirtualDesktopPoint,
)


class CoordinateError(Exception):
    """Base exception for coordinate transformation errors."""


class PointNotInTopologyError(CoordinateError):
    """Raised when a coordinate cannot be resolved within active display topology."""


class CoordinateTransformer:
    """Transforms coordinates across the 4-level display hierarchy:

    1. Global Desktop Space (Windows Virtual Desktop physical pixels)
    2. Containing Monitor Identification
    3. Monitor-Local Space (physical pixels relative to monitor origin)
    4. Unity World Space (meters in unified scene)
    """

    def __init__(self, base_pixels_per_meter: float = 500.0) -> None:
        if not math.isfinite(base_pixels_per_meter) or base_pixels_per_meter <= 0:
            raise ValueError("base_pixels_per_meter must be positive")
        self.base_ppm = base_pixels_per_meter

    def global_to_monitor_local(
        self,
        global_x: int,
        global_y: int,
        topology: DisplayTopology,
    ) -> tuple[MonitorDescriptor, int, int] | None:
        """Find containing monitor and map to local physical pixel coordinates.

        Returns None if point lies in a non-display gap or outside all monitors.
        """
        monitor = topology.find_monitor(global_x, global_y)
        if monitor is None:
            return None
        local_x = global_x - monitor.rect.x
        local_y = global_y - monitor.rect.y
        return monitor, local_x, local_y

    def monitor_local_to_global(
        self,
        local_point: MonitorLocalPoint,
        topology: DisplayTopology,
    ) -> VirtualDesktopPoint:
        """Map monitor-local physical coordinates back to global desktop pixels."""
        for m in topology.monitors:
            if m.id == local_point.monitor_id:
                return VirtualDesktopPoint(
                    x=m.rect.x + local_point.x,
                    y=m.rect.y + local_point.y,
                )
        raise PointNotInTopologyError(f"Monitor {local_point.monitor_id} not found in topology")

    def global_to_world(
        self,
        global_x: int,
        global_y: int,
        topology: DisplayTopology,
    ) -> UnityWorldPoint:
        """Continuous physical-pixel plane; DPI changes avatar size, not position.

        Gap coordinates have a mathematical projection but are not actionable
        display targets. Callers must validate/clamp them separately.
        """
        primary = next((m for m in topology.monitors if m.primary), None)
        if primary is None:
            raise PointNotInTopologyError("Topology has no active monitors")
        return UnityWorldPoint(
            x=(global_x - primary.rect.x) / self.base_ppm,
            y=-(global_y - primary.rect.y) / self.base_ppm,
            z=0.0,
        )

    def world_to_global(
        self,
        world_point: UnityWorldPoint,
        topology: DisplayTopology,
        target_monitor_id: str | None = None,
    ) -> VirtualDesktopPoint:
        """Invert without nearest-monitor guesses or monitor hints."""
        primary = next((m for m in topology.monitors if m.primary), None)
        if primary is None:
            raise PointNotInTopologyError("Topology has no active monitors")
        if target_monitor_id is not None and not any(
            m.id == target_monitor_id for m in topology.monitors
        ):
            raise PointNotInTopologyError(f"Monitor {target_monitor_id} not found in topology")
        return VirtualDesktopPoint(
            x=round(world_point.x * self.base_ppm + primary.rect.x),
            y=round(-world_point.y * self.base_ppm + primary.rect.y),
        )
