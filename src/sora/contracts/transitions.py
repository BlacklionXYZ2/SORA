"""Explicit task, run, and approval transition matrices."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from .errors import InvalidTransition
from .models import ApprovalStatus, RunStatus, TaskStatus

TASK_TRANSITIONS: Mapping[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PLANNED: frozenset({TaskStatus.QUEUED, TaskStatus.CANCELLED}),
    TaskStatus.QUEUED: frozenset(
        {TaskStatus.ROUTING, TaskStatus.CANCEL_REQUESTED, TaskStatus.CANCELLED}
    ),
    TaskStatus.ROUTING: frozenset(
        {
            TaskStatus.REASONING,
            TaskStatus.WORKING,
            TaskStatus.FAILED,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.INTERRUPTED,
        }
    ),
    TaskStatus.REASONING: frozenset(
        {
            TaskStatus.WORKING,
            TaskStatus.WAITING_FOR_PERMISSION,
            TaskStatus.WAITING_FOR_INPUT,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.INTERRUPTED,
        }
    ),
    TaskStatus.WORKING: frozenset(
        {
            TaskStatus.REASONING,
            TaskStatus.WAITING_FOR_PERMISSION,
            TaskStatus.WAITING_FOR_INPUT,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.INTERRUPTED,
        }
    ),
    TaskStatus.WAITING_FOR_PERMISSION: frozenset(
        {TaskStatus.REASONING, TaskStatus.WORKING, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED}
    ),
    TaskStatus.WAITING_FOR_INPUT: frozenset(
        {TaskStatus.REASONING, TaskStatus.WORKING, TaskStatus.CANCEL_REQUESTED, TaskStatus.FAILED}
    ),
    TaskStatus.CANCEL_REQUESTED: frozenset(
        {TaskStatus.CANCELLED, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.INTERRUPTED}
    ),
    TaskStatus.INTERRUPTED: frozenset(
        {TaskStatus.QUEUED, TaskStatus.ROUTING, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.COMPLETED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.FAILED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.CANCELLED: frozenset({TaskStatus.QUEUED}),
}

RUN_TRANSITIONS: Mapping[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.LAUNCHING, RunStatus.CANCELLED}),
    RunStatus.LAUNCHING: frozenset(
        {RunStatus.RUNNING, RunStatus.UNCERTAIN, RunStatus.FAILED, RunStatus.CANCEL_REQUESTED}
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_FOR_PERMISSION,
            RunStatus.WAITING_FOR_INPUT,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCEL_REQUESTED,
            RunStatus.INTERRUPTED,
            RunStatus.UNCERTAIN,
        }
    ),
    RunStatus.WAITING_FOR_PERMISSION: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED, RunStatus.FAILED, RunStatus.INTERRUPTED}
    ),
    RunStatus.WAITING_FOR_INPUT: frozenset(
        {RunStatus.RUNNING, RunStatus.CANCEL_REQUESTED, RunStatus.FAILED, RunStatus.INTERRUPTED}
    ),
    RunStatus.CANCEL_REQUESTED: frozenset(
        {RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.UNCERTAIN}
    ),
    RunStatus.INTERRUPTED: frozenset({RunStatus.FAILED, RunStatus.CANCELLED}),
    RunStatus.UNCERTAIN: frozenset(
        {RunStatus.RUNNING, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.COMPLETED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}

APPROVAL_TRANSITIONS: Mapping[ApprovalStatus, frozenset[ApprovalStatus]] = {
    ApprovalStatus.PENDING: frozenset(
        {
            ApprovalStatus.APPROVED,
            ApprovalStatus.DENIED,
            ApprovalStatus.EXPIRED,
            ApprovalStatus.CANCELLED,
        }
    ),
    ApprovalStatus.APPROVED: frozenset(),
    ApprovalStatus.DENIED: frozenset(),
    ApprovalStatus.EXPIRED: frozenset(),
    ApprovalStatus.CANCELLED: frozenset(),
}


def _validate_transition[StatusT: StrEnum](
    lifecycle: str,
    current: StatusT,
    requested: StatusT,
    matrix: Mapping[StatusT, frozenset[StatusT]],
) -> None:
    if requested not in matrix[current]:
        raise InvalidTransition(lifecycle, current.value, requested.value)


def validate_task_transition(current: TaskStatus, requested: TaskStatus) -> None:
    _validate_transition("task", current, requested, TASK_TRANSITIONS)


def validate_run_transition(current: RunStatus, requested: RunStatus) -> None:
    _validate_transition("run", current, requested, RUN_TRANSITIONS)


def validate_approval_transition(current: ApprovalStatus, requested: ApprovalStatus) -> None:
    _validate_transition("approval", current, requested, APPROVAL_TRANSITIONS)
