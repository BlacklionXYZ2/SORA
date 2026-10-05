"""Owner-local, bounded task-attempt evidence; no trace/capture/private patch projection."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from sora.contracts.base import ContractModel, Identifier, NonEmptyText
from sora.contracts.models import AgentRunRecord, TaskStatus


class RunHistoryItem(ContractModel):
    run: AgentRunRecord
    result_id: Identifier | None = None


class TaskRunPage(ContractModel):
    task_id: Identifier
    task_status: TaskStatus
    active_run_id: Identifier | None = None
    runs: Annotated[tuple[RunHistoryItem, ...], Field(max_length=100)] = ()
    next_cursor: Annotated[str | None, Field(max_length=1024)] = None
    total: Annotated[int, Field(ge=0)]
    projection_revision: Annotated[int, Field(ge=0)]
    evidence_note: NonEmptyText


class RunArtifact(ContractModel):
    kind: str
    path: NonEmptyText
    reference_ids: Annotated[tuple[Identifier, ...], Field(max_length=64)] = ()


class TaskRunEvidence(ContractModel):
    task_id: Identifier
    run: AgentRunRecord
    result: dict[str, object] | None = None
    omitted_items: dict[str, int] = Field(default_factory=dict)
    text_truncated: bool = False
    artifacts: Annotated[tuple[RunArtifact, ...], Field(max_length=65)] = ()
    projection_revision: Annotated[int, Field(ge=0)]
    evidence_note: NonEmptyText
