"""Deterministic duplicate and stream-order classification."""

from __future__ import annotations

from enum import StrEnum

from .errors import ContractErrorCode, EventOrderingViolation
from .models import EventEnvelope


class EventOrder(StrEnum):
    FIRST = "first"
    NEXT = "next"
    DUPLICATE = "duplicate"


def classify_event_order(previous: EventEnvelope | None, current: EventEnvelope) -> EventOrder:
    if previous is None:
        return EventOrder.FIRST
    if previous.event_id == current.event_id:
        return EventOrder.DUPLICATE
    if previous.stream_id != current.stream_id:
        raise EventOrderingViolation(
            ContractErrorCode.EVENT_STREAM_MISMATCH,
            f"cannot compare streams {previous.stream_id!r} and {current.stream_id!r}",
        )
    if current.sequence <= previous.sequence:
        raise EventOrderingViolation(
            ContractErrorCode.EVENT_SEQUENCE_REGRESSION,
            f"event sequence regressed from {previous.sequence} to {current.sequence}",
        )
    if current.sequence != previous.sequence + 1:
        raise EventOrderingViolation(
            ContractErrorCode.EVENT_SEQUENCE_GAP,
            f"event sequence gap: expected {previous.sequence + 1}, got {current.sequence}",
        )
    return EventOrder.NEXT
