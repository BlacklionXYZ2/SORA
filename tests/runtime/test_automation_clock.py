"""Pure schedule rules, not evidence of an installed scheduler or agent execution."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from sora.contracts.automation import (
    AutomationBehavior,
    AutomationOccurrence,
    AutomationSlot,
    AutomationSpec,
    DailyTrigger,
    IntervalTrigger,
    OneOffTrigger,
    WeeklyTrigger,
)
from sora.runtime.automation_clock import missed_disposition, next_slot


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def spec(**changes: Any) -> AutomationSpec:
    return AutomationSpec(
        name="Read-only fixture",
        trigger=DailyTrigger(kind="daily", timezone="UTC", local_time="09:00"),
        behavior=AutomationBehavior(intent="Summarize the selected fixture"),
        **changes,
    )


def test_once_aware_boundary_and_interval_anchor_are_restart_stable() -> None:
    at = instant("2026-10-04T09:00:00Z")
    one = OneOffTrigger(kind="once", timezone="Europe/London", at=at)
    slot = next_slot(one, at - timedelta(seconds=1))
    assert slot is not None and slot.decision_at == at and slot.planned_local == "2026-10-04T10:00"
    assert next_slot(one, at) is None and next_slot(one, at + timedelta(seconds=1)) is None
    interval = IntervalTrigger(
        kind="interval", timezone="Europe/London", anchor_at=at, seconds=14400
    )
    assert next_slot(interval, at - timedelta(seconds=1)) == slot
    later = next_slot(interval, at + timedelta(days=50, minutes=30))
    assert later is not None and later.decision_at == at + timedelta(days=50, hours=4)
    assert (
        next_slot(
            IntervalTrigger.model_validate_json(interval.model_dump_json()),
            at + timedelta(days=50, minutes=30),
        )
        == later
    )


def test_daily_keeps_wall_time_while_interval_keeps_elapsed_time_across_dst() -> None:
    daily = DailyTrigger(kind="daily", timezone="Europe/London", local_time="09:00")
    before = instant("2026-03-28T09:00:00Z")
    following = next_slot(daily, before)
    assert following is not None and following.decision_at == instant("2026-03-29T08:00:00Z")
    interval = IntervalTrigger(
        kind="interval", timezone="Europe/London", anchor_at=before, seconds=86400
    )
    elapsed = next_slot(interval, before)
    assert elapsed is not None and elapsed.decision_at == instant("2026-03-29T09:00:00Z")
    assert elapsed.planned_local == "2026-03-29T10:00"


def test_gap_is_skipped_at_transition_not_run_at_shifted_wall_time() -> None:
    daily = DailyTrigger(kind="daily", timezone="Europe/London", local_time="01:30")
    gap = next_slot(daily, instant("2026-03-28T02:00:00Z"))
    assert gap is not None and gap.disposition == "skip_nonexistent"
    assert gap.planned_local == "2026-03-29T01:30" and gap.decision_at == instant(
        "2026-03-29T01:00:00Z"
    )
    assert (
        missed_disposition(
            spec(missed_policy="run_once"), gap, gap.decision_at, recovered=False, overlapping=False
        )
        == "skip_nonexistent"
    )
    following = next_slot(daily, gap.decision_at)
    assert following is not None and following.planned_local == "2026-03-30T01:30"


def test_repeated_autumn_time_runs_only_first_fold() -> None:
    daily = DailyTrigger(kind="daily", timezone="Europe/London", local_time="01:30")
    first = next_slot(daily, instant("2026-10-24T02:00:00Z"))
    assert first is not None and first.decision_at == instant("2026-10-25T00:30:00Z")
    next_day = next_slot(daily, first.decision_at)
    assert next_day is not None and next_day.decision_at == instant("2026-10-26T01:30:00Z")
    assert next_slot(daily, instant("2026-10-25T01:00:00Z")) == next_day


def test_whole_day_and_half_hour_gaps_do_not_erase_following_valid_slots() -> None:
    samoa = DailyTrigger(kind="daily", timezone="Pacific/Apia", local_time="09:00")
    gap = next_slot(samoa, instant("2011-12-29T20:00:00Z"))
    assert (
        gap is not None
        and gap.planned_local == "2011-12-30T09:00"
        and gap.disposition == "skip_nonexistent"
    )
    following = next_slot(samoa, gap.decision_at)
    assert following is not None and following.planned_local == "2011-12-31T09:00"
    assert following.disposition == "due" and following.decision_at > gap.decision_at
    lord_howe = DailyTrigger(kind="daily", timezone="Australia/Lord_Howe", local_time="02:15")
    half_gap = next_slot(lord_howe, instant("2026-10-02T00:00:00Z"))
    assert half_gap is not None and half_gap.disposition == "due"  # October3 is still valid.
    half_gap = next_slot(lord_howe, half_gap.decision_at)
    assert half_gap is not None and half_gap.disposition == "skip_nonexistent"
    assert half_gap.planned_local == "2026-10-04T02:15"


def test_weekday_selection_is_explicit_sorted_and_bounded() -> None:
    weekly = WeeklyTrigger(
        kind="weekly", timezone="Asia/Kathmandu", local_time="09:00", weekdays=(4, 0)
    )
    assert weekly.weekdays == (0, 4)
    monday = next_slot(weekly, instant("2026-10-04T00:00:00Z"))
    assert monday is not None and monday.decision_at == instant("2026-10-05T03:15:00Z")
    friday = next_slot(weekly, monday.decision_at)
    assert friday is not None and friday.planned_local == "2026-10-09T09:00"


@pytest.mark.parametrize(
    "changes",
    [
        {"weekdays": ()},
        {"weekdays": (0, 0)},
        {"weekdays": (7,)},
        {"weekdays": (True,)},
        {"local_time": "25:00"},
        {"local_time": "9:00"},
        {"timezone": "Unknown/Zone"},
        {"timezone": "../private"},
        {"timezone": "C:/private"},
    ],
)
def test_invalid_calendar_fields_are_rejected(changes: dict[str, Any]) -> None:
    values: dict[str, Any] = {
        "kind": "weekly",
        "timezone": "UTC",
        "local_time": "09:00",
        "weekdays": (0,),
    }
    with pytest.raises(ValidationError):
        WeeklyTrigger.model_validate({**values, **changes})


@pytest.mark.parametrize("seconds", [0, 59, True, "3600", 31_536_001])
def test_interval_bounds_and_naive_timestamps_are_rejected(seconds: Any) -> None:
    with pytest.raises(ValidationError):
        IntervalTrigger(
            kind="interval", timezone="UTC", anchor_at=datetime.now(UTC), seconds=seconds
        )
    with pytest.raises(ValidationError):
        OneOffTrigger(kind="once", timezone="UTC", at=datetime(2026, 10, 4))
    with pytest.raises(ValueError, match="UTC offset"):
        next_slot(
            DailyTrigger(kind="daily", timezone="UTC", local_time="09:00"), datetime(2026, 10, 4)
        )


@pytest.mark.parametrize(
    "recovered,lag,policy,overlap,expected",
    [
        (False, -1, "skip", False, "wait"),
        (False, 0, "skip", False, "admit"),
        (False, 5, "skip", False, "admit"),
        (False, 6, "skip", False, "skip_missed"),
        (True, 1, "skip", False, "skip_missed"),
        (True, 300, "run_once", False, "admit"),
        (True, 301, "run_once", False, "skip_missed"),
        (False, 1, "run_once", True, "skip_overlap"),
    ],
)
def test_missed_overlap_and_bounded_catchup_decisions(
    recovered: bool,
    lag: int,
    policy: str,
    overlap: bool,
    expected: str,
) -> None:
    configuration = spec(missed_policy=policy)
    slot = next_slot(configuration.trigger, instant("2026-10-04T08:00:00Z"))
    assert slot is not None
    assert (
        missed_disposition(
            configuration,
            slot,
            slot.decision_at + timedelta(seconds=lag),
            recovered=recovered,
            overlapping=overlap,
        )
        == expected
    )


def test_no_definition_or_occurrence_can_claim_effects_from_configuration() -> None:
    slot = next_slot(spec().trigger, instant("2026-10-04T08:00:00Z"))
    assert slot is not None
    values = {
        "occurrence_id": "occurrence-fixture",
        "automation_id": "automation-fixture",
        "definition_version": 1,
        "origin": "scheduled",
        "slot": slot,
        "status": "reserved",
        "behavior": spec().behavior,
        "recorded_at": slot.decision_at,
    }
    occurrence = AutomationOccurrence.model_validate(values)
    assert occurrence.task_id is None and occurrence.run_id is None
    with pytest.raises(ValidationError):
        AutomationOccurrence.model_validate({**values, "status": "completed"})
    with pytest.raises(ValidationError):
        AutomationOccurrence.model_validate(
            {**values, "task_id": "task-unadmitted", "run_id": "run-unadmitted"}
        )
    with pytest.raises(ValidationError):
        AutomationOccurrence.model_validate({**values, "authorized_by": "owner"})
    with pytest.raises(ValidationError):
        AutomationSlot.model_validate({**slot.model_dump(), "planned_local": "2026-02-31T09:00"})
