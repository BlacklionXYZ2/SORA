"""SORA desktop objects, canonical projections, and scoped affordances."""

from .affordances import (
    DesktopObjectAffordanceBridge,
    DesktopObjectAffordanceError,
    DesktopObjectDefinition,
)
from .kanban import KanbanBoardProjection, KanbanCard, KanbanColumn, project_tasks_to_kanban

__all__ = [
    "DesktopObjectAffordanceBridge",
    "DesktopObjectAffordanceError",
    "DesktopObjectDefinition",
    "KanbanBoardProjection",
    "KanbanCard",
    "KanbanColumn",
    "project_tasks_to_kanban",
]
