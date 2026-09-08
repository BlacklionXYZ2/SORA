from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sora.contracts.base import ContractModel
from sora.contracts.codec import decode_contract, encode_contract
from sora.contracts.models import (
    AgentRunRecord,
    AgentSessionRecord,
    ApprovalRequest,
    CapabilityGrant,
    CapabilityRequest,
    EventEnvelope,
    NormalizedResult,
    PatchEnvelope,
    ProviderCapabilities,
    ProviderRequest,
    TaskRecord,
)

from .helpers import example_text


@pytest.mark.parametrize(
    ("model", "fixture"),
    [
        (TaskRecord, "task-record.json"),
        (AgentRunRecord, "agent-run-record.json"),
        (AgentSessionRecord, "agent-session-record.json"),
        (ProviderCapabilities, "provider-capabilities.json"),
        (ProviderRequest, "provider-request.json"),
        (PatchEnvelope, "patch-envelope.json"),
        (NormalizedResult, "normalized-result.json"),
        (EventEnvelope, "event-envelope.json"),
        (CapabilityRequest, "capability-request.json"),
        (CapabilityGrant, "capability-grant.json"),
        (ApprovalRequest, "approval-request.json"),
    ],
)
def test_records_round_trip(model: type[ContractModel], fixture: str) -> None:
    value = decode_contract(model, example_text("valid", fixture))
    assert decode_contract(model, encode_contract(value)) == value
    assert value.schema_version == "1.0"


def test_task_run_and_session_are_separate_records() -> None:
    task = TaskRecord.model_validate_json(example_text("valid", "task-record.json"))
    run = AgentRunRecord.model_validate_json(example_text("valid", "agent-run-record.json"))
    session = AgentSessionRecord.model_validate_json(
        example_text("valid", "agent-session-record.json")
    )

    assert task.task_id == run.task_id == session.task_id
    assert task.active_run_id == run.run_id
    assert run.native_session_id == session.native_session_id
    assert task.task_id != run.run_id != session.session_id


def test_completed_result_without_conclusion_is_rejected() -> None:
    with pytest.raises(ValidationError, match="completed results require conclusion"):
        NormalizedResult.model_validate_json(example_text("scenarios", "malformed-result.json"))


def test_offset_naive_timestamp_is_rejected() -> None:
    payload = TaskRecord.model_validate_json(example_text("valid", "task-record.json")).model_dump()
    payload["created_at"] = datetime(2026, 9, 7, 17, 0)
    payload["updated_at"] = datetime(2026, 9, 7, 17, 0, 1, tzinfo=UTC)

    with pytest.raises(ValidationError, match="UTC offset"):
        TaskRecord.model_validate(payload)
