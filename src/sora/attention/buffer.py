"""Volatile bounded in-memory cursor tracking buffer."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta

from sora.contracts.base import StrictModel, require_aware


class CursorSample(StrictModel):
    timestamp: datetime
    x: int
    y: int
    buttons: tuple[str, ...] = ()
    target_element: str | None = None


class CursorRingBuffer:
    """Bounded volatile ring buffer of cursor samples."""

    def __init__(self, capacity: int = 1_000) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self._samples: deque[CursorSample] = deque(maxlen=capacity)

    def append(self, sample: CursorSample) -> None:
        require_aware(sample.timestamp, "sample.timestamp")
        self._samples.append(sample)

    def __len__(self) -> int:
        return len(self._samples)

    def get_sample_at(
        self,
        timestamp: datetime,
        tolerance_seconds: float = 1.0,
    ) -> CursorSample | None:
        require_aware(timestamp, "timestamp")
        if not self._samples:
            return None

        best_sample: CursorSample | None = None
        min_delta = timedelta(seconds=tolerance_seconds)

        for s in self._samples:
            delta = abs(s.timestamp - timestamp)
            if delta <= min_delta:
                min_delta = delta
                best_sample = s

        return best_sample

    def get_recent_samples(
        self,
        duration_seconds: float = 5.0,
        now: datetime | None = None,
    ) -> tuple[CursorSample, ...]:
        ref_time = now or datetime.now(UTC)
        require_aware(ref_time, "now")
        cutoff = ref_time - timedelta(seconds=duration_seconds)
        return tuple(s for s in self._samples if s.timestamp >= cutoff)
