"""Volatile capacity- and time-bounded in-memory cursor tracking buffer."""

from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field, field_validator

from sora.contracts.base import ContractModel, Identifier, require_aware

type CursorButton = Literal["left", "right", "middle", "x1", "x2"]


class CursorSample(ContractModel):
    timestamp: datetime
    x: int
    y: int
    buttons: tuple[CursorButton, ...] = ()
    target_element: Identifier | None = None
    topology_revision: int = Field(default=1, ge=1)
    monotonic_ns: int | None = Field(default=None, ge=0)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        return require_aware(value, "timestamp")

    @field_validator("buttons")
    @classmethod
    def unique_buttons(cls, value: tuple[CursorButton, ...]) -> tuple[CursorButton, ...]:
        if len(set(value)) != len(value):
            raise ValueError("cursor buttons must be unique")
        return value


class CursorRingBuffer:
    """Bounded volatile ring buffer of cursor samples."""

    def __init__(self, capacity: int = 1_000, max_age_seconds: float = 8.0) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        if not 0 < max_age_seconds <= 60:
            raise ValueError("max_age_seconds must be between 0 and 60")
        self.capacity = capacity
        self.max_age_seconds = max_age_seconds
        self._samples: deque[CursorSample] = deque(maxlen=capacity)
        self._latest_seen: datetime | None = None

    def append(self, sample: CursorSample) -> None:
        if self._samples and sample.timestamp < self._samples[-1].timestamp:
            raise ValueError("cursor samples must be appended in timestamp order")
        self._samples.append(sample)
        self._latest_seen = sample.timestamp
        self.prune(sample.timestamp)

    def append_many(self, samples: tuple[CursorSample, ...]) -> None:
        for sample in samples:
            self.append(sample)

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def oldest(self) -> CursorSample | None:
        return self._samples[0] if self._samples else None

    @property
    def newest(self) -> CursorSample | None:
        return self._samples[-1] if self._samples else None

    @property
    def latest_seen(self) -> datetime | None:
        return self._latest_seen

    def clear(self) -> None:
        self._samples.clear()
        self._latest_seen = None

    def prune(self, now: datetime | None = None) -> int:
        ref_time = now or datetime.now(UTC)
        require_aware(ref_time, "now")
        cutoff = ref_time - timedelta(seconds=self.max_age_seconds)
        removed = 0
        while self._samples and self._samples[0].timestamp < cutoff:
            self._samples.popleft()
            removed += 1
        return removed

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
        if duration_seconds < 0:
            raise ValueError("duration_seconds cannot be negative")
        self.prune(ref_time)
        cutoff = ref_time - timedelta(seconds=duration_seconds)
        return tuple(s for s in self._samples if cutoff <= s.timestamp <= ref_time)
