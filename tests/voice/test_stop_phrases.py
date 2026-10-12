"""Spoken interruptions: the natural ways to make her stop talking, and what they must not catch."""

from __future__ import annotations

import pytest

from sora.contracts.voice import VoiceConversationIntent
from sora.voice.intents import classify_voice_intent

STOP = VoiceConversationIntent.STOP_SPEAKING


@pytest.mark.parametrize("text", [
    "Sora, stop.", "Stop!", "Stop, Sora.", "Okay Sora, stop.", "Sora stop talking",
    "Stop speaking", "Be quiet", "Sora, quiet please", "Shh", "Hush", "Wait.", "Hold on",
    "Sora, that's enough.", "Never mind", "Hey Sora, please stop.", "Silence yourself",
])
def test_natural_interruptions_stop_her(text: str) -> None:
    assert classify_voice_intent(text) is STOP


@pytest.mark.parametrize(("text", "intent"), [
    ("Wait, what about the other window?", VoiceConversationIntent.DIALOGUE),
    ("Stop the music in Spotify", VoiceConversationIntent.DIALOGUE),
    ("Don't stop", VoiceConversationIntent.DIALOGUE),
    ("Stop it", VoiceConversationIntent.CANCEL_TASK),  # unchanged: stops a running task
    ("Stop the task", VoiceConversationIntent.CANCEL_TASK),
])
def test_longer_requests_are_not_interruptions(text: str, intent: VoiceConversationIntent) -> None:
    assert classify_voice_intent(text) is intent
