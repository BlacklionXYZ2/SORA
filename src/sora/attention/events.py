"""Bounded P13.1 deduplication, debounce, and attention policy."""

from __future__ import annotations

from collections import OrderedDict, deque
from datetime import UTC, datetime, timedelta

from sora.contracts.desktop_events import (
    DesktopAttentionHint,
    DesktopEvent,
    DesktopEventBatchResult,
    DesktopEventDecision,
    DesktopEventDisposition,
    DesktopEventKind,
)
from sora.contracts.models import TaskStatus


class DesktopEventAttentionPolicy:
    """Classify volatile events; this object cannot call inference, speech, or persistence."""

    _CONTEXT_KINDS = frozenset(
        {
            DesktopEventKind.FOREGROUND_CHANGED,
            DesktopEventKind.WINDOW_OPENED,
            DesktopEventKind.WINDOW_CLOSED,
            DesktopEventKind.DIALOG_OPENED,
            DesktopEventKind.DIALOG_CLOSED,
        }
    )

    def __init__(
        self,
        *,
        seen_capacity: int = 1_024,
        recent_capacity: int = 256,
        debounce_seconds: float = 0.35,
        invalidation_cooldown_seconds: float = 0.5,
    ) -> None:
        if seen_capacity < 1 or recent_capacity < 1:
            raise ValueError("desktop event capacities must be positive")
        if not 0 <= debounce_seconds <= 5:
            raise ValueError("debounce_seconds must be between 0 and 5")
        if not 0 <= invalidation_cooldown_seconds <= 5:
            raise ValueError("invalidation cooldown must be between 0 and 5")
        self.seen_capacity = seen_capacity
        self.recent_capacity = recent_capacity
        self.debounce_seconds = debounce_seconds
        self.invalidation_cooldown_seconds = invalidation_cooldown_seconds
        self._seen: OrderedDict[str, DesktopEvent] = OrderedDict()
        self._semantic_last: OrderedDict[tuple[object, ...], datetime] = OrderedDict()
        self._last_invalidation: OrderedDict[str, datetime] = OrderedDict()
        self._recent: deque[DesktopEventDecision] = deque(maxlen=recent_capacity)

    @property
    def recent(self) -> tuple[DesktopEventDecision, ...]:
        return tuple(self._recent)

    def clear(self) -> None:
        self._seen.clear()
        self._semantic_last.clear()
        self._last_invalidation.clear()
        self._recent.clear()

    def known(self, event_id: str) -> DesktopEvent | None:
        return self._seen.get(event_id)

    def classify(
        self,
        event: DesktopEvent,
        *,
        device_id: str,
        now: datetime | None = None,
    ) -> DesktopEventDecision:
        evaluated_at = now or datetime.now(UTC)
        age = (evaluated_at - event.occurred_at).total_seconds()
        if age < -5 or age > 30:
            raise ValueError("desktop event timestamp must be live")

        previous = self._seen.get(event.event_id)
        if previous is not None:
            if previous != event:
                raise ValueError("desktop event ID reused with different payload")
            decision = self._decision(
                event,
                DesktopEventDisposition.DEDUPLICATED,
                DesktopAttentionHint.NONE,
            )
            self._recent.append(decision)
            return decision

        self._seen[event.event_id] = event
        self._seen.move_to_end(event.event_id)
        while len(self._seen) > self.seen_capacity:
            self._seen.popitem(last=False)

        semantic_key = self._semantic_key(event, device_id)
        semantic_previous = self._semantic_last.get(semantic_key)
        debounced = semantic_previous is not None and abs(
            (event.occurred_at - semantic_previous).total_seconds()
        ) < self.debounce_seconds
        self._semantic_last[semantic_key] = max(
            event.occurred_at,
            semantic_previous or event.occurred_at,
        )
        self._semantic_last.move_to_end(semantic_key)
        while len(self._semantic_last) > self.seen_capacity:
            self._semantic_last.popitem(last=False)
        if debounced:
            decision = self._decision(
                event,
                DesktopEventDisposition.DEBOUNCED,
                DesktopAttentionHint.NONE,
            )
            self._recent.append(decision)
            return decision

        context_invalidated = False
        if event.kind in self._CONTEXT_KINDS:
            last_invalidation = self._last_invalidation.get(device_id)
            context_invalidated = last_invalidation is None or (
                event.occurred_at - last_invalidation
            ) >= timedelta(seconds=self.invalidation_cooldown_seconds)
            if context_invalidated:
                self._last_invalidation[device_id] = event.occurred_at
                self._last_invalidation.move_to_end(device_id)
                while len(self._last_invalidation) > self.seen_capacity:
                    self._last_invalidation.popitem(last=False)

        decision = self._decision(
            event,
            DesktopEventDisposition.ACCEPTED,
            self._attention_hint(event),
            context_invalidated=context_invalidated,
        )
        self._recent.append(decision)
        return decision

    @staticmethod
    def result(decisions: tuple[DesktopEventDecision, ...]) -> DesktopEventBatchResult:
        return DesktopEventBatchResult(
            decisions=decisions,
            accepted_count=sum(
                decision.disposition is DesktopEventDisposition.ACCEPTED
                for decision in decisions
            ),
            deduplicated_count=sum(
                decision.disposition is DesktopEventDisposition.DEDUPLICATED
                for decision in decisions
            ),
            debounced_count=sum(
                decision.disposition is DesktopEventDisposition.DEBOUNCED
                for decision in decisions
            ),
            context_invalidation_count=sum(
                decision.context_invalidated for decision in decisions
            ),
        )

    @staticmethod
    def _semantic_key(event: DesktopEvent, device_id: str) -> tuple[object, ...]:
        if event.kind is DesktopEventKind.TASK_CHANGED:
            return device_id, event.kind, event.task_id, event.task_status
        return device_id, event.kind, event.window_handle, event.process_id

    @staticmethod
    def _attention_hint(event: DesktopEvent) -> DesktopAttentionHint:
        if event.kind is DesktopEventKind.DIALOG_OPENED:
            return DesktopAttentionHint.IMPORTANT
        if event.kind is DesktopEventKind.TASK_CHANGED and event.task_status in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }:
            return DesktopAttentionHint.NOTICE
        return DesktopAttentionHint.NONE

    @staticmethod
    def _decision(
        event: DesktopEvent,
        disposition: DesktopEventDisposition,
        attention_hint: DesktopAttentionHint,
        *,
        context_invalidated: bool = False,
    ) -> DesktopEventDecision:
        return DesktopEventDecision(
            event_id=event.event_id,
            kind=event.kind,
            disposition=disposition,
            attention_hint=attention_hint,
            context_invalidated=context_invalidated,
        )
