"""Typed contract failures suitable for application/API translation."""

from __future__ import annotations

from enum import StrEnum


class ContractErrorCode(StrEnum):
    INVALID_TRANSITION = "invalid_transition"
    EVENT_STREAM_MISMATCH = "event_stream_mismatch"
    EVENT_SEQUENCE_REGRESSION = "event_sequence_regression"
    EVENT_SEQUENCE_GAP = "event_sequence_gap"


class ContractViolation(ValueError):
    """Base error with a stable machine-readable code."""

    def __init__(self, code: ContractErrorCode, message: str):
        super().__init__(message)
        self.code = code


class InvalidTransition(ContractViolation):
    def __init__(self, lifecycle: str, current: str, requested: str):
        super().__init__(
            ContractErrorCode.INVALID_TRANSITION,
            f"invalid {lifecycle} transition: {current} -> {requested}",
        )


class EventOrderingViolation(ContractViolation):
    pass
