"""Gesture recognition over volatile cursor trajectories."""

from __future__ import annotations

import math

from .buffer import CursorSample


def detect_click(
    samples: tuple[CursorSample, ...],
    *,
    button: str = "left",
    max_duration_seconds: float = 0.6,
    max_distance_px: float = 12.0,
) -> CursorSample | None:
    """Detect the most recent press/release transition without synthesizing input."""
    for release_index in range(len(samples) - 1, 0, -1):
        release = samples[release_index]
        if button not in samples[release_index - 1].buttons or button in release.buttons:
            continue

        press_index = release_index - 1
        while press_index > 0 and button in samples[press_index - 1].buttons:
            press_index -= 1
        press = samples[press_index]
        duration = (release.timestamp - press.timestamp).total_seconds()
        distance = math.hypot(release.x - press.x, release.y - press.y)
        if 0 <= duration <= max_duration_seconds and distance <= max_distance_px:
            return release
    return None


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
    min_duration_seconds: float = 0.2,
    max_duration_seconds: float = 4.0,
    min_average_velocity: float = 20.0,
    max_average_velocity: float = 2_500.0,
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

    duration = (samples[-1].timestamp - samples[0].timestamp).total_seconds()
    if duration < min_duration_seconds or duration > max_duration_seconds:
        return None

    # Aspect ratio check
    aspect = width / height if height > 0 else 0
    if aspect < 0.4 or aspect > 2.5:
        return None

    # Path length & closure check
    path_len = sum(math.hypot(xs[i] - xs[i - 1], ys[i] - ys[i - 1]) for i in range(1, len(samples)))
    perimeter_est = 2 * (width + height)
    if path_len < perimeter_est * 0.6 or path_len > perimeter_est * 3.0:
        return None
    velocity = path_len / duration
    if velocity < min_average_velocity or velocity > max_average_velocity:
        return None

    # Closure: distance between start and end point
    start_end_dist = math.hypot(xs[-1] - xs[0], ys[-1] - ys[0])
    diag = math.hypot(width, height)
    if start_end_dist > diag * max_closure_ratio:
        return None

    # A backtracking line can be long and closed. Require meaningful enclosed area and winding.
    twice_area = sum(
        xs[index] * ys[(index + 1) % len(samples)] - xs[(index + 1) % len(samples)] * ys[index]
        for index in range(len(samples))
    )
    area = abs(twice_area) / 2
    if area < width * height * 0.35:
        return None

    center_x = sum(xs) / len(xs)
    center_y = sum(ys) / len(ys)
    angles = [math.atan2(y - center_y, x - center_x) for x, y in zip(xs, ys, strict=True)]
    winding = 0.0
    for previous, current in zip(angles, angles[1:], strict=False):
        delta = current - previous
        while delta <= -math.pi:
            delta += 2 * math.pi
        while delta > math.pi:
            delta -= 2 * math.pi
        winding += delta
    if not 1.5 * math.pi <= abs(winding) <= 3.0 * math.pi:
        return None

    return (min_x, min_y, width, height)
