"""P11.1 semantic presentation state and style contract acceptance."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sora.contracts.embodiment import (
    EmbodimentCommand,
    EmbodimentPresentationState,
    EmbodimentSemanticAction,
    EmbodimentVerb,
)


def command(**updates: object) -> EmbodimentCommand:
    payload: dict[str, object] = {
        "command_id": "p11-presentation-fixture",
        "verb": EmbodimentVerb.SET_STATE,
        "state": EmbodimentPresentationState.THINKING,
        "topology_revision": 1,
        "created_at": datetime.now(UTC),
    }
    payload.update(updates)
    return EmbodimentCommand.model_validate(payload)


def test_semantic_states_and_optional_style_are_presentation_only() -> None:
    thinking = command(presentation_style="focused")
    assert thinking.state is EmbodimentPresentationState.THINKING
    assert thinking.presentation_style == "focused"
    for state in (
        EmbodimentPresentationState.IDLE,
        EmbodimentPresentationState.THINKING,
        EmbodimentPresentationState.LISTENING,
        EmbodimentPresentationState.SPEAKING,
        EmbodimentPresentationState.WAITING_FOR_AGENT,
        EmbodimentPresentationState.READING,
        EmbodimentPresentationState.TYPING,
        EmbodimentPresentationState.SITTING,
        EmbodimentPresentationState.LEANING,
        EmbodimentPresentationState.CLIMBING,
    ):
        assert command(command_id=f"state-{state}", state=state).state is state


def test_motion_states_remain_derived_and_action_profiles_do_not_prove_effects() -> None:
    for state in (EmbodimentPresentationState.MOVING, EmbodimentPresentationState.LOOKING):
        with pytest.raises(ValueError, match="derived"):
            command(state=state)

    phase = command(
        command_id="p11-action-profile",
        verb=EmbodimentVerb.PRESENTATION_PHASE,
        state=None,
        semantic_action_id="semantic-action-fixture",
        semantic_action=EmbodimentSemanticAction.POINT,
        semantic_phase="reach",
        presentation_style="careful",
    )
    assert phase.semantic_action is EmbodimentSemanticAction.POINT
    assert phase.presentation_style == "careful"

    with pytest.raises(ValueError, match="presentation_phase or interaction_start"):
        command(semantic_action=EmbodimentSemanticAction.PRESS)
    with pytest.raises(ValueError, match="set_state, presentation_phase or interaction_start"):
        command(
            verb=EmbodimentVerb.LOOK_AT,
            state=None,
            target_point={"x": 10, "y": 10},
            presentation_style="focused",
        )
