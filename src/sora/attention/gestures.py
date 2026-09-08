"""Gesture recognition over volatile cursor trajectories."""

from __future__ import annotations

import math

from .buffer import CursorSample


def detect_hover(
    samples: tuple[CursorSample, ...],
    min_duration_seconds: float = 0.5,
    max_distance_px: float = 15.0,
) -> tuple[int, int] | None:
    """Detect if pointer was held relatively stable for at least min_duration."""
    if len(samples) < 2:
        return None

    duration = (samples[-1].timestamp - samples[0].timestamp).total_seconds()
    if duration < min_duration_seconds:
        return None

    ref_x, ref_y = samples[0].x, samples[0].y
    for s in samples[1:]:
        dist = math.hypot(s.x - ref_x, s.y - ref_y)
        if dist > max_distance_px:
            return None

    # Return centroid
    mean_x = int(sum(s.x for s in samples) / len(samples))
    mean_y = int(sum(s.y for s in samples) / len(samples))
    return (mean_x, mean_y)


def recognize_circle(
    samples: tuple[CursorSample, ...],
    min_points: int = 8,
    max_closure_ratio: float = 0.35,
) -> tuple[int, int, int, int] | None:
    """Recognize a circling gesture and return its bounding box (x, y, width, height)."""
    if len(samples) < min_points:
        return None

    xs = [s.x for s in samples]
    ys = [s.y for s in samples]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    width = max_x - min_x
    height = max_y - min_y

    if width < 20 or height < 20:
        return None

    # Aspect ratio check
    aspect = width / height if height > 0 else 0
    if aspect < 0.25 or aspect > 4.0:
        return None

    # Path length & closure check
    path_len = sum(
        math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1])
        for i in range(1, len(samples))
    )
    perimeter_est = 2 * (width + height)
    if path_len < perimeter_est * 0.6:
        return None

    # Closure: distance between start and end point
    start_end_dist = math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
    diag = math.hypot(width, height)
    if start_end_dist > diag * max_closure_ratio:
        return None

    return (min_x, min_y, width, height)
