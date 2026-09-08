from __future__ import annotations

from datetime import UTC, datetime

from sora.contracts.models import AgentRunRecord, AgentSessionRecord, PatchEnvelope, TaskRecord
from sora.persistence.records import MessageRecord
from tests.contracts.helpers import example_text


def sample_task() -> TaskRecord:
    return TaskRecord.model_validate_json(example_text("valid", "task-record.json"))


def sample_run() -> AgentRunRecord:
    return AgentRunRecord.model_validate_json(example_text("valid", "agent-run-record.json"))


def sample_session() -> AgentSessionRecord:
    return AgentSessionRecord.model_validate_json(
        example_text("valid", "agent-session-record.json")
    )


def sample_patch() -> PatchEnvelope:
    return PatchEnvelope.model_validate_json(example_text("valid", "patch-envelope.json"))


def sample_message() -> MessageRecord:
    return MessageRecord(
        message_id="message-history-001",
        conversation_id="conversation-001",
        owner_id="owner-local",
        project_id="project-sora",
        role="user",
        content="Persist this representative history entry.",
        provenance="user input",
        created_at=datetime(2026, 9, 7, 17, 0, tzinfo=UTC),
    )
