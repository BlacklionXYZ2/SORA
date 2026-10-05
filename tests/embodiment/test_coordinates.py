"""Tests for multi-monitor coordinate engine against canonical shared fixtures."""

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
from sora.embodiment.coordinates import CoordinateTransformer


def load_canonical_fixtures() -> list[dict[str, Any]]:
    fixture_path = Path(__file__).parents[2] / "contracts" / "fixtures" / "coordinate_fixtures.json"
    with open(fixture_path, encoding="utf-8") as f:
        data = json.load(f)
    return cast(list[dict[str, Any]], data["fixtures"])


CANONICAL_FIXTURES = load_canonical_fixtures()


@pytest.mark.parametrize(
    "fixture_data",
    CANONICAL_FIXTURES,
    ids=[f["fixture_id"] for f in CANONICAL_FIXTURES],
)
def test_coordinate_fixtures_forward_inverse_and_gaps(fixture_data: dict[str, Any]) -> None:
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
    transformer = CoordinateTransformer(base_pixels_per_meter=500.0)

    for pt in fixture_data["test_points"]:
        gx, gy = pt["global_px"]
        is_gap = pt["is_in_gap"]

        local_res = transformer.global_to_monitor_local(gx, gy, topology)

        if is_gap:
            assert local_res is None, (
                f"Point ({gx}, {gy}) should be in a gap, but was matched to monitor"
            )
        else:
            assert local_res is not None, (
                f"Point ({gx}, {gy}) should be inside a monitor, but was None"
            )
            mon, lx, ly = local_res
            assert mon.id == pt["expected_monitor_id"]
            assert (lx, ly) == tuple(pt["expected_monitor_local_px"])

            # Test bidirectional round trip
            world_pt = transformer.global_to_world(gx, gy, topology)
            round_trip = transformer.world_to_global(world_pt, topology, target_monitor_id=mon.id)

            err_x = abs(round_trip.x - gx)
            err_y = abs(round_trip.y - gy)

            assert err_x <= 1, f"X round-trip error > 1px: orig={gx}, got={round_trip.x}"
            assert err_y <= 1, f"Y round-trip error > 1px: orig={gy}, got={round_trip.y}"
