"""Exact, bounded editor-context handoff contracts for P10.4."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from sora.contracts.base import ContractModel, Identifier, NonEmptyText, require_aware


class EditorPosition(ContractModel):
    """One-based Unicode-code-point position; range ends are exclusive."""

    line: int = Field(ge=1, le=10_000_000)
    column: int = Field(ge=1, le=10_000_000)


class EditorSelection(ContractModel):
    start: EditorPosition
    end: EditorPosition

    @model_validator(mode="after")
    def ordered_nonempty_range(self) -> EditorSelection:
        if (self.end.line, self.end.column) <= (self.start.line, self.start.column):
            raise ValueError("editor selection end must follow start")
        return self


class EditorContextRequest(ContractModel):
    """Metadata emitted by an authenticated cooperating editor integration."""

    source: Literal["app_integration"] = "app_integration"
    editor_name: Identifier
    repository_root: str = Field(min_length=1, max_length=4096)
    relative_file_path: str = Field(min_length=1, max_length=4096)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: EditorSelection
    selected_text: str = Field(min_length=1, max_length=4096)
    desktop_target_id: Identifier
    captured_at: datetime

    @model_validator(mode="after")
    def validate_request(self) -> EditorContextRequest:
        require_aware(self.captured_at, "captured_at")
        if "\x00" in self.repository_root or "\x00" in self.relative_file_path:
            raise ValueError("editor paths cannot contain NUL bytes")
        return self


class EditorContextSnapshot(ContractModel):
    """Verified task context persisted under the task's normal retention policy."""

    context_id: Identifier
    owner_id: Identifier
    device_id: Identifier
    project_id: Identifier | None = None
    source: Literal["app_integration"] = "app_integration"
    editor_name: Identifier
    repository_root: str = Field(min_length=1, max_length=4096)
    relative_file_path: str = Field(min_length=1, max_length=4096)
    document_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: EditorSelection
    selected_text: str = Field(min_length=1, max_length=4096)
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    desktop_target_id: Identifier
    captured_at: datetime
    verified_at: datetime

    @model_validator(mode="after")
    def validate_times(self) -> EditorContextSnapshot:
        require_aware(self.captured_at, "captured_at")
        require_aware(self.verified_at, "verified_at")
        if self.verified_at < self.captured_at:
            raise ValueError("verified_at cannot precede captured_at")
        return self

    def provider_context(self) -> str:
        """Render an exact block without relying on markdown delimiters."""
        selection = self.selection
        return "\n".join(
            (
                "EDITOR_CONTEXT_V1",
                f"context_id={self.context_id}",
                "editor_json=" + json.dumps(self.editor_name),
                "repository_root_json=" + json.dumps(self.repository_root),
                "relative_file_path_json=" + json.dumps(self.relative_file_path),
                f"document_sha256={self.document_sha256}",
                (
                    "selection="
                    f"{selection.start.line}:{selection.start.column}-"
                    f"{selection.end.line}:{selection.end.column}"
                ),
                f"selection_sha256={self.selection_sha256}",
                "selection_text_json=" + json.dumps(self.selected_text),
            )
        )


class EditorTaskRequest(ContractModel):
    intent: NonEmptyText
    editor_context: EditorContextRequest
    idempotency_key: Identifier | None = None
    explicit_provider: Identifier | None = None


class EditorFinding(ContractModel):
    """Provider-reported finding bound to one verified editor snapshot."""

    finding_id: Identifier
    context_id: Identifier
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_line: int = Field(ge=1, le=10_000_000)
    end_line: int = Field(ge=1, le=10_000_000)
    summary: str = Field(min_length=1, max_length=1024)
    evidence_refs: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def ordered_lines(self) -> EditorFinding:
        if self.end_line < self.start_line:
            raise ValueError("finding end_line cannot precede start_line")
        return self


class EditorFindingPresentationRequest(ContractModel):
    context_id: Identifier
    result_id: Identifier
    finding_id: Identifier
    marker_duration_seconds: float = Field(default=5.0, gt=0, le=30, allow_inf_nan=False)
