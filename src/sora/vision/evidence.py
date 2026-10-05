"""Owner-scoped volatile storage for normalized P13.3 vision evidence."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

from sora.contracts.vision import VisionEvidence


@dataclass(frozen=True, slots=True)
class _StoredEvidence:
    evidence: VisionEvidence
    owner_id: str
    device_id: str
    project_id: str | None


class VisionEvidenceStore:
    """Evidence is process-local and disappears on expiry, eviction, or shutdown."""

    def __init__(self, *, capacity: int = 256) -> None:
        if not 1 <= capacity <= 4096:
            raise ValueError("vision evidence capacity must be between 1 and 4096")
        self.capacity = capacity
        self._evidence: OrderedDict[tuple[str, str, str | None, str], _StoredEvidence] = (
            OrderedDict()
        )

    @property
    def count(self) -> int:
        return len(self._evidence)

    def put_many(
        self,
        evidence: tuple[VisionEvidence, ...],
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> None:
        evaluated_at = now or datetime.now(UTC)
        self.prune(evaluated_at)
        keys = [(owner_id, device_id, project_id, record.evidence_id) for record in evidence]
        if len(keys) != len(set(keys)) or any(key in self._evidence for key in keys):
            raise ValueError("vision evidence ID was already used in this scope")
        if any(record.expires_at <= evaluated_at for record in evidence):
            raise ValueError("vision evidence expired before storage")
        for key, record in zip(keys, evidence, strict=True):
            self._evidence[key] = _StoredEvidence(
                evidence=record,
                owner_id=owner_id,
                device_id=device_id,
                project_id=project_id,
            )
        while len(self._evidence) > self.capacity:
            self._evidence.popitem(last=False)

    def list_for_capture(
        self,
        capture_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> tuple[VisionEvidence, ...]:
        self.prune(now or datetime.now(UTC))
        return tuple(
            stored.evidence
            for key, stored in self._evidence.items()
            if key[:3] == (owner_id, device_id, project_id)
            and stored.evidence.capture_id == capture_id
        )

    def get(
        self,
        evidence_id: str,
        *,
        owner_id: str,
        device_id: str,
        project_id: str | None,
        now: datetime | None = None,
    ) -> VisionEvidence | None:
        self.prune(now or datetime.now(UTC))
        key = (owner_id, device_id, project_id, evidence_id)
        stored = self._evidence.get(key)
        if stored is None:
            return None
        self._evidence.move_to_end(key)
        return stored.evidence

    def prune(self, now: datetime) -> int:
        expired = [
            key for key, stored in self._evidence.items() if stored.evidence.expires_at <= now
        ]
        for key in expired:
            del self._evidence[key]
        return len(expired)

    def clear(self) -> None:
        self._evidence.clear()
