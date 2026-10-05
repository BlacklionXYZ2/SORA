from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.authorization_helpers import persist_operation_grant

from sora.contracts.embodiment import (
    EmbodimentCommand,
    EmbodimentFeedbackEvent,
    EmbodimentFeedbackKind,
    EmbodimentSupportSurface,
    EmbodimentVerb,
    ScreenRect,
    VirtualDesktopPoint,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime


def surface(
    *,
    surface_id: str = "window:fixture",
    state: str = "active",
    rect: ScreenRect | None = None,
    observed_at: datetime | None = None,
) -> EmbodimentSupportSurface:
    observed = observed_at or datetime.now(UTC)
    return EmbodimentSupportSurface.model_validate(
        {
            "surface_id": surface_id,
            "kind": "window_top",
            "rect": (rect or ScreenRect(x=300, y=500, width=600, height=400)).model_dump(),
            "state": state,
            "observed_at": observed,
            "expires_at": observed + timedelta(seconds=10),
        }
    )


def support_command(*surfaces: EmbodimentSupportSurface) -> EmbodimentCommand:
    return EmbodimentCommand(
        command_id="support-snapshot",
        verb=EmbodimentVerb.SET_SUPPORTS,
        support_surfaces=surfaces,
        topology_revision=1,
        created_at=datetime.now(UTC),
    )


def feedback(
    event_id: str,
    kind: EmbodimentFeedbackKind = EmbodimentFeedbackKind.POKED,
    *,
    occurred_at: datetime | None = None,
    subject_id: str | None = None,
    correlation_id: str | None = None,
) -> EmbodimentFeedbackEvent:
    return EmbodimentFeedbackEvent(
        event_id=event_id,
        kind=kind,
        occurred_at=occurred_at or datetime.now(UTC),
        topology_revision=1,
        position=VirtualDesktopPoint(x=400, y=500),
        subject_id=subject_id,
        correlation_id=correlation_id,
    )


def test_support_contract_is_bounded_short_lived_and_command_specific() -> None:
    assert support_command(surface()).support_surfaces[0].state == "active"
    with pytest.raises(ValidationError, match="unique"):
        support_command(surface(), surface())
    with pytest.raises(ValidationError, match="at most 32"):
        support_command(*(surface(surface_id=f"window:{index}") for index in range(33)))
    with pytest.raises(ValidationError, match="30 seconds"):
        EmbodimentSupportSurface(
            surface_id="window:long",
            rect=ScreenRect(x=0, y=0, width=100, height=100),
            observed_at=datetime.now(UTC),
            expires_at=datetime.now(UTC) + timedelta(seconds=60),
        )
    with pytest.raises(ValidationError, match="requires set_supports"):
        EmbodimentCommand(
            command_id="wrong-verb",
            verb=EmbodimentVerb.HIDE_MARKER,
            support_surfaces=(surface(),),
            created_at=datetime.now(UTC),
        )


@pytest.mark.asyncio
async def test_core_dispatches_only_live_in_bounds_selected_surfaces(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path,
            identity_root=Path(__file__).resolve().parents[2] / "identity",
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        queue = runtime.register_embodiment_queue()
        await persist_operation_grant(
            runtime, "embodiment.command", grant_id="grant-supports"
        )
        args = {"grant_id": "grant-supports", "device_id": "device-local"}
        command = support_command(surface())
        await runtime.dispatch_embodiment_command(command, **args)
        assert queue.get_nowait() == command

        with pytest.raises(ValueError, match="fit on one active display"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(
                    update={
                        "command_id": "outside",
                        "support_surfaces": (
                            surface(rect=ScreenRect(x=1800, y=500, width=600, height=400)),
                        ),
                    }
                ),
                **args,
            )
        stale = datetime.now(UTC) - timedelta(seconds=29)
        with pytest.raises(ValueError, match="not live"):
            await runtime.dispatch_embodiment_command(
                command.model_copy(
                    update={
                        "command_id": "expired",
                        "support_surfaces": (surface(observed_at=stale),),
                    }
                ),
                **args,
            )
    finally:
        await runtime.close()


def test_feedback_contract_requires_meaningful_terminal_and_support_identity() -> None:
    with pytest.raises(ValidationError, match="correlation_id"):
        feedback("event:terminal", EmbodimentFeedbackKind.COMPLETED)
    with pytest.raises(ValidationError, match="subject_id"):
        feedback("event:support", EmbodimentFeedbackKind.SUPPORT_REMOVED)
    event = feedback(
        "event:complete",
        EmbodimentFeedbackKind.COMPLETED,
        correlation_id="interaction:fixture",
    )
    assert event.correlation_id == "interaction:fixture"


@pytest.mark.asyncio
async def test_core_deduplicates_cools_down_and_rate_bounds_feedback(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path,
            identity_root=Path(__file__).resolve().parents[2] / "identity",
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        start = datetime.now(UTC)
        first = feedback("event:first", occurred_at=start)
        assert runtime.record_embodiment_feedback(first)
        assert not runtime.record_embodiment_feedback(first)
        with pytest.raises(ValueError, match="different payload"):
            runtime.record_embodiment_feedback(
                first.model_copy(update={"kind": EmbodimentFeedbackKind.CLICKED})
            )
        assert not runtime.record_embodiment_feedback(
            feedback("event:cooldown", occurred_at=start + timedelta(milliseconds=100))
        )
        assert runtime.record_embodiment_feedback(
            feedback("event:after-cooldown", occurred_at=start + timedelta(milliseconds=600))
        )

        terminal = feedback(
            "event:completed",
            EmbodimentFeedbackKind.COMPLETED,
            occurred_at=start,
            correlation_id="interaction:one",
        )
        assert runtime.record_embodiment_feedback(terminal)
        assert not runtime.record_embodiment_feedback(
            feedback(
                "event:failed-late",
                EmbodimentFeedbackKind.FAILED,
                occurred_at=start + timedelta(milliseconds=300),
                correlation_id="interaction:one",
            )
        )
        with pytest.raises(ValueError, match="timestamp"):
            runtime.record_embodiment_feedback(
                feedback("event:stale", occurred_at=start - timedelta(seconds=31))
            )
        with pytest.raises(ValueError, match="outside"):
            runtime.record_embodiment_feedback(
                feedback("event:outside").model_copy(
                    update={"position": VirtualDesktopPoint(x=-100, y=-100)}
                )
            )

        accepted_before = len(runtime.embodiment_feedback)
        for index in range(30):
            runtime.record_embodiment_feedback(
                feedback(
                    f"event:burst:{index}",
                    EmbodimentFeedbackKind.LANDED,
                    occurred_at=start + timedelta(milliseconds=index),
                    subject_id=f"support:{index}",
                )
            )
        assert len(runtime.embodiment_feedback) - accepted_before <= 17
        projection = runtime.get_embodiment_projection()
        assert projection["recent_feedback"][-1]["kind"] == "landed"
        assert len(projection["recent_feedback"]) <= 20
    finally:
        await runtime.close()
