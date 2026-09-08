from __future__ import annotations

import json
from typing import cast

import pytest

from sora.contracts.errors import ContractErrorCode, EventOrderingViolation
from sora.contracts.events import EventOrder, classify_event_order
from sora.contracts.models import EventEnvelope, PatchEnvelope
from sora.contracts.patches import PatchDisposition, evaluate_patch

from .helpers import example_text


def test_patch_preflight_distinguishes_apply_duplicate_and_conflict() -> None:
    patch = PatchEnvelope.model_validate_json(example_text("valid", "patch-envelope.json"))

    applicable = evaluate_patch(
        patch,
        applied_idempotency_keys=set(),
        entity_versions={("task", "task-001"): 3},
    )
    duplicate = evaluate_patch(
        patch,
        applied_idempotency_keys={"patch-once-001"},
        entity_versions={("task", "task-001"): 3},
    )
    conflict = evaluate_patch(
        patch,
        applied_idempotency_keys=set(),
        entity_versions={("task", "task-001"): 4},
    )

    assert applicable.disposition is PatchDisposition.APPLICABLE
    assert duplicate.disposition is PatchDisposition.DUPLICATE
    assert conflict.disposition is PatchDisposition.CONFLICT
    assert conflict.conflicts[0].actual_version == 4


def test_stale_patch_scenario_fixture_matches_policy() -> None:
    scenario = cast(dict[str, object], json.loads(example_text("scenarios", "stale-patch.json")))
    patch = PatchEnvelope.model_validate_json(example_text("valid", "patch-envelope.json"))
    versions = cast(dict[str, int], scenario["entity_versions"])
    entity_versions = {
        (parts[0], parts[1]): value
        for key, value in versions.items()
        if len(parts := key.split(":", 1)) == 2
    }
    evaluation = evaluate_patch(
        patch,
        applied_idempotency_keys=set(),
        entity_versions=entity_versions,
    )

    assert evaluation.disposition.value == scenario["expected_disposition"]


def test_event_duplicate_and_contiguous_delivery() -> None:
    first = EventEnvelope.model_validate_json(example_text("valid", "event-envelope.json"))
    second = first.model_copy(update={"event_id": "event-002", "sequence": 2})

    assert classify_event_order(None, first) is EventOrder.FIRST
    assert classify_event_order(first, first) is EventOrder.DUPLICATE
    assert classify_event_order(first, second) is EventOrder.NEXT


def test_duplicate_event_scenario_fixture_matches_policy() -> None:
    scenario = cast(
        dict[str, object], json.loads(example_text("scenarios", "duplicate-event.json"))
    )
    event = EventEnvelope.model_validate_json(example_text("valid", "event-envelope.json"))

    assert scenario["deliveries"] == 2
    assert classify_event_order(event, event).value == scenario["expected_second_disposition"]


def test_event_gap_requires_explicit_recovery() -> None:
    first = EventEnvelope.model_validate_json(example_text("valid", "event-envelope.json"))
    gap = first.model_copy(update={"event_id": "event-003", "sequence": 3})

    with pytest.raises(EventOrderingViolation) as raised:
        classify_event_order(first, gap)

    assert raised.value.code is ContractErrorCode.EVENT_SEQUENCE_GAP
