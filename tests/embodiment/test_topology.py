"""Tests for display topology management, gap clamping, and revision invalidation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from sora.contracts.embodiment import (
    DisplayTopology,
    MonitorDescriptor,
    ScreenRect,
)
from sora.embodiment.topology import DisplayTopologyManager


def load_canonical_fixtures() -> list[dict[str, Any]]:
    fixture_path = Path(__file__).parents[2] / "contracts" / "fixtures" / "coordinate_fixtures.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[dict[str, Any]], data["fixtures"])


CANONICAL_FIXTURES = load_canonical_fixtures()


def test_topology_validation() -> None:
    rect = ScreenRect(x=0, y=0, width=1920, height=1080)
    # Fail: zero primary monitors
    with pytest.raises(ValueError, match="must contain exactly 1 primary monitor"):
        DisplayTopology(
            virtual_desktop=rect,
            monitors=(
                MonitorDescriptor(id="M1", primary=False, rect=rect),
                MonitorDescriptor(id="M2", primary=False, rect=rect),
            ),
        )

    # Fail: duplicate monitor IDs
    with pytest.raises(ValueError, match="monitor IDs must be unique"):
        DisplayTopology(
            virtual_desktop=rect,
            monitors=(
                MonitorDescriptor(id="M1", primary=True, rect=rect),
                MonitorDescriptor(id="M1", primary=False, rect=rect),
            ),
        )


@pytest.mark.parametrize(
    "fixture_data",
    CANONICAL_FIXTURES,
    ids=[f["fixture_id"] for f in CANONICAL_FIXTURES],
)
def test_topology_gap_clamping(fixture_data: dict[str, Any]) -> None:
    vd_rect = ScreenRect(**fixture_data["virtual_desktop"])
    monitors = tuple(
        MonitorDescriptor(
            id=m["id"],
            primary=m["primary"],
            rect=ScreenRect(**m["rect"]),
            dpi_scale=m["dpi_scale"],
            orientation=m["orientation"],
        )
        for m in fixture_data["monitors"]
    )
    topology = DisplayTopology(virtual_desktop=vd_rect, monitors=monitors, revision=1)
    manager = DisplayTopologyManager(topology)

    for pt in fixture_data["test_points"]:
        gx, gy = pt["global_px"]
        if pt.get("is_in_gap"):
            clamped = manager.clamp_to_nearest_display(gx, gy)
            expected_clamp = pt["expected_clamped_px"]
            assert (clamped.x, clamped.y) == tuple(expected_clamp), (
                f"Clamping for ({gx}, {gy}) in {fixture_data['fixture_id']} failed: "
                f"expected {expected_clamp}, got ({clamped.x}, {clamped.y})"
            )
            # The clamped point itself must be on a display
            assert manager.is_point_on_display(clamped.x, clamped.y)


def test_topology_revision_advancement() -> None:
    m1 = MonitorDescriptor(
        id="DISPLAY1",
        primary=True,
        rect=ScreenRect(x=0, y=0, width=1920, height=1080),
    )
    manager = DisplayTopologyManager()
    assert manager.revision == 1
    assert manager.validate_revision(1)
    assert not manager.validate_revision(2)

    # Add second monitor
    m2 = MonitorDescriptor(
        id="DISPLAY2",
        primary=False,
        rect=ScreenRect(x=1920, y=0, width=1920, height=1080),
    )
    new_rev = manager.update_topology((m1, m2))
    assert new_rev == 2
    assert manager.revision == 2
    assert not manager.validate_revision(1)
    assert manager.validate_revision(2)
    assert manager.topology.virtual_desktop.width == 3840
