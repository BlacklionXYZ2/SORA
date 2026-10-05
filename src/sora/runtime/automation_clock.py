"""Pure deterministic time decisions, no timer, persistence, task admission or side effects."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sora.contracts.automation import (
    AutomationSlot,
    AutomationSpec,
    AutomationTrigger,
    IntervalTrigger,
    OneOffTrigger,
    WeeklyTrigger,
)
from sora.contracts.base import require_aware


def _utc(value: datetime) -> datetime:
    return require_aware(value, "scheduler timestamp").astimezone(UTC)


def _instant_slot(trigger: OneOffTrigger | IntervalTrigger, instant: datetime) -> AutomationSlot:
    utc = _utc(instant)
    return AutomationSlot(
        slot_key="instant:" + utc.isoformat(),
        decision_at=utc,
        planned_local=utc.astimezone(ZoneInfo(trigger.timezone)).strftime("%Y-%m-%dT%H:%M"),
        timezone=trigger.timezone,
    )


def next_slot(trigger: AutomationTrigger, after: datetime) -> AutomationSlot | None:
    """Return the first slot strictly after an aware boundary; interval anchors never reset."""
    boundary = _utc(after)
    if isinstance(trigger, OneOffTrigger):
        return _instant_slot(trigger, trigger.at) if _utc(trigger.at) > boundary else None
    if isinstance(trigger, IntervalTrigger):
        anchor = _utc(trigger.anchor_at)
        elapsed = boundary - anchor
        step = timedelta(seconds=trigger.seconds)
        index = max(0, elapsed // step + 1)
        return _instant_slot(trigger, anchor + index * step)
    zone = ZoneInfo(trigger.timezone)
    local_date = boundary.astimezone(zone).date()
    local_clock = time.fromisoformat(trigger.local_time)
    for offset in range(9):  # At least the next eligible weekly day, including after today's slot.
        day = local_date + timedelta(days=offset)
        if isinstance(trigger, WeeklyTrigger) and day.weekday() not in trigger.weekdays:
            continue
        naive = datetime.combine(day, local_clock)
        first = naive.replace(tzinfo=zone, fold=0)
        instant = first.astimezone(UTC)
        roundtrip = instant.astimezone(zone).replace(tzinfo=None)
        missing = roundtrip != naive
        # A gap has no execution instant. Record the skip at the transition's first
        # valid instant, not at fold0's shifted wall clock (which can collide with a
        # legitimate following-day run in zones with a whole-day transition).
        if missing:
            alternate = naive.replace(tzinfo=zone, fold=1).astimezone(UTC)
            lower, upper = sorted((instant, alternate))
            while (upper - lower).total_seconds() > 1:
                middle = lower + timedelta(seconds=int((upper - lower).total_seconds()) // 2)
                if middle.astimezone(zone).replace(tzinfo=None) < naive:
                    lower = middle
                else:
                    upper = middle
            instant = upper
        if instant > boundary:
            return AutomationSlot(
                slot_key="local:" + naive.strftime("%Y-%m-%dT%H:%M"),
                decision_at=instant,
                planned_local=naive.strftime("%Y-%m-%dT%H:%M"),
                timezone=trigger.timezone,
                disposition="skip_nonexistent" if missing else "due",
            )
    raise ValueError("No bounded next calendar slot available")


def missed_disposition(
    spec: AutomationSpec,
    slot: AutomationSlot,
    now: datetime,
    *,
    recovered: bool,
    overlapping: bool,
    grace_seconds: int = 5,
) -> Literal["wait", "admit", "skip_nonexistent", "skip_overlap", "skip_missed"]:
    """Decide one persisted slot; no backlog enumeration or claim of external execution."""
    if grace_seconds < 0 or grace_seconds > 60:
        raise ValueError("Scheduler grace must be between0 and60 seconds")
    lag = (_utc(now) - _utc(slot.decision_at)).total_seconds()
    if lag < 0:
        return "wait"
    if slot.disposition == "skip_nonexistent":
        return "skip_nonexistent"
    if overlapping:
        return "skip_overlap"
    if recovered or lag > grace_seconds:
        return (
            "admit"
            if spec.missed_policy == "run_once" and lag <= spec.catch_up_seconds
            else "skip_missed"
        )
    return "admit"
