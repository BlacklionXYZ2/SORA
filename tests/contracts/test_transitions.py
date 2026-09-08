from __future__ import annotations

import pytest

from sora.contracts.errors import ContractErrorCode, InvalidTransition
from sora.contracts.models import ApprovalStatus, RunStatus, TaskStatus
from sora.contracts.transitions import (
    validate_approval_transition,
    validate_run_transition,
    validate_task_transition,
)


def test_expected_task_and_run_progressions_are_valid() -> None:
    validate_task_transition(TaskStatus.QUEUED, TaskStatus.ROUTING)
    validate_task_transition(TaskStatus.ROUTING, TaskStatus.REASONING)
    validate_task_transition(TaskStatus.REASONING, TaskStatus.WORKING)
    validate_task_transition(TaskStatus.WORKING, TaskStatus.COMPLETED)

    validate_run_transition(RunStatus.PENDING, RunStatus.LAUNCHING)
    validate_run_transition(RunStatus.LAUNCHING, RunStatus.UNCERTAIN)
    validate_run_transition(RunStatus.UNCERTAIN, RunStatus.COMPLETED)


def test_explicit_task_retry_preserves_terminal_run() -> None:
    validate_task_transition(TaskStatus.FAILED, TaskStatus.QUEUED)

    with pytest.raises(InvalidTransition) as raised:
        validate_run_transition(RunStatus.FAILED, RunStatus.PENDING)

    assert raised.value.code is ContractErrorCode.INVALID_TRANSITION


def test_cancel_request_preserves_race_outcomes() -> None:
    validate_task_transition(TaskStatus.CANCEL_REQUESTED, TaskStatus.CANCELLED)
    validate_task_transition(TaskStatus.CANCEL_REQUESTED, TaskStatus.COMPLETED)
    validate_run_transition(RunStatus.CANCEL_REQUESTED, RunStatus.UNCERTAIN)


def test_approval_decisions_are_terminal() -> None:
    validate_approval_transition(ApprovalStatus.PENDING, ApprovalStatus.APPROVED)
    with pytest.raises(InvalidTransition):
        validate_approval_transition(ApprovalStatus.APPROVED, ApprovalStatus.DENIED)
