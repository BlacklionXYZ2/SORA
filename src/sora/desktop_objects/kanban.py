"""Projection of canonical tasks to a desktop Kanban board object."""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from sora.contracts.base import NonEmptyText, StrictModel
from sora.contracts.models import TaskRecord, TaskStatus


class KanbanColumn(StrEnum):
    TODO = "TODO"
    DOING = "DOING"
    DONE = "DONE"


class KanbanCard(StrictModel):
    task_id: str
    summary: NonEmptyText
    column: KanbanColumn
    status: TaskStatus
    specialist: str | None = None
    needs_attention: bool = False


class KanbanBoardProjection(StrictModel):
    board_id: str
    cards: tuple[KanbanCard, ...] = ()


def project_tasks_to_kanban(
    tasks: tuple[TaskRecord, ...],
    *,
    board_id: str = "sora-kanban-main",
    summaries: Mapping[str, str] | None = None,
) -> KanbanBoardProjection:
    """Project canonical tasks onto Kanban columns deterministically."""
    cards: list[KanbanCard] = []

    for task in tasks:
        # Determine column and specialist mapping
        specialist = task.effective_backend
        if specialist == "auto":
            specialist = None

        if task.status is TaskStatus.PLANNED:
            col = KanbanColumn.TODO
            needs_att = False
        elif task.status in {
            TaskStatus.QUEUED,
            TaskStatus.ROUTING,
            TaskStatus.REASONING,
            TaskStatus.WORKING,
            TaskStatus.WAITING_FOR_PERMISSION,
            TaskStatus.WAITING_FOR_INPUT,
            TaskStatus.CANCEL_REQUESTED,
            TaskStatus.INTERRUPTED,
        }:
            col = KanbanColumn.DOING
            needs_att = task.status in {
                TaskStatus.WAITING_FOR_PERMISSION,
                TaskStatus.WAITING_FOR_INPUT,
                TaskStatus.CANCEL_REQUESTED,
                TaskStatus.INTERRUPTED,
            }
        elif task.status is TaskStatus.COMPLETED:
            col = KanbanColumn.DONE
            needs_att = False
        else:
            # FAILED, CANCELLED, INTERRUPTED
            col = KanbanColumn.DONE
            needs_att = True

        summary = (summaries or {}).get(task.task_id) or (
            task.constraints[0] if task.constraints else f"Task {task.task_id}"
        )

        cards.append(
            KanbanCard(
                task_id=task.task_id,
                summary=summary,
                column=col,
                status=task.status,
                specialist=specialist,
                needs_attention=needs_att,
            )
        )

    return KanbanBoardProjection(board_id=board_id, cards=tuple(cards))
