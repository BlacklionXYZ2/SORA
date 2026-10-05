"""Display topology manager, revision invalidation, and gap clamping."""

from __future__ import annotations

import math

from sora.contracts.embodiment import (
    DisplayTopology,
    MonitorDescriptor,
    ScreenRect,
    VirtualDesktopPoint,
)


class StaleTopologyRevisionError(Exception):
    """Raised when a command references an obsolete display topology revision."""


class DisplayTopologyManager:
    """Manages active Windows display topology, invalidation, and boundary clamping."""

    def __init__(self, initial_topology: DisplayTopology | None = None) -> None:
        if initial_topology is None:
            initial_topology = DisplayTopology(
                virtual_desktop=ScreenRect(x=0, y=0, width=1920, height=1080),
                monitors=(
                    MonitorDescriptor(
                        id="PRIMARY",
                        primary=True,
                        rect=ScreenRect(x=0, y=0, width=1920, height=1080),
                        dpi_scale=1.0,
                        orientation="landscape",
                    ),
                ),
                revision=1,
            )
        self._topology = initial_topology

    @property
    def topology(self) -> DisplayTopology:
        return self._topology

    @property
    def revision(self) -> int:
        return self._topology.revision

    def update_topology(
        self,
        monitors: tuple[MonitorDescriptor, ...],
        virtual_desktop: ScreenRect | None = None,
    ) -> int:
        """Update display topology on hardware/DPI changes and advance revision number."""
        if not monitors:
            raise ValueError("monitors cannot be empty")

        if virtual_desktop is None:
            min_x = min(m.rect.x for m in monitors)
            min_y = min(m.rect.y for m in monitors)
            max_r = max(m.rect.right for m in monitors)
            max_b = max(m.rect.bottom for m in monitors)
            virtual_desktop = ScreenRect(
                x=min_x,
                y=min_y,
                width=max_r - min_x,
                height=max_b - min_y,
            )

        new_revision = self._topology.revision + 1
        self._topology = DisplayTopology(
            virtual_desktop=virtual_desktop,
            monitors=monitors,
            revision=new_revision,
        )
        return new_revision

    def validate_revision(self, command_revision: int) -> bool:
        """Check if an incoming command's topology revision matches current active topology."""
        return command_revision == self._topology.revision

    def find_monitor(self, x: int, y: int) -> MonitorDescriptor | None:
        return self._topology.find_monitor(x, y)

    def is_point_on_display(self, x: int, y: int) -> bool:
        return self._topology.is_point_on_display(x, y)

    def clamp_to_nearest_display(self, x: int, y: int) -> VirtualDesktopPoint:
        """Clamp a point (e.g. in a non-display gap or offscreen) to the closest valid pixel."""
        if not self._topology.monitors:
            return VirtualDesktopPoint(x=x, y=y)

        # If already on a display, return directly
        if self.is_point_on_display(x, y):
            return VirtualDesktopPoint(x=x, y=y)

        best_x = x
        best_y = y
        best_dist = float("inf")

        for m in self._topology.monitors:
            # Clamp to monitor rectangle (inclusive bounds: [x, right - 1], [y, bottom - 1])
            clamped_x = max(m.rect.x, min(x, m.rect.right - 1))
            clamped_y = max(m.rect.y, min(y, m.rect.bottom - 1))
            dist = math.hypot(x - clamped_x, y - clamped_y)
            if dist < best_dist:
                best_dist = dist
                best_x = clamped_x
                best_y = clamped_y

        return VirtualDesktopPoint(x=best_x, y=best_y)
