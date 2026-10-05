"""Deterministic P14.5 spoken control and deictic-reference classification."""

from __future__ import annotations

import re

from sora.contracts.voice import VoiceConversationIntent

_STOP_SPEAKING = re.compile(
    r"^\s*(?:(?:hey\s+)?sora[,:]?\s+)?(?:please\s+)?"
    r"(?:stop\s+(?:speaking|talking)|be\s+quiet|quiet\s+please|silence(?:\s+yourself)?)"
    r"[.!?\s]*$",
    re.IGNORECASE,
)
_CANCEL_TASK = re.compile(
    r"\b(?:cancel|abort|stop)\b.*\b(?:task|job|run|cody|codex|hermes|"
    r"antigravity|ag|him|her|them|it)\b",
    re.IGNORECASE,
)
_STEER_TASK = re.compile(
    r"\b(?:tell|ask|steer|instruct)\b.*\b(?:cody|codex|hermes|"
    r"antigravity|ag|him|her|them|it)\b",
    re.IGNORECASE,
)
_NEW_WORK = re.compile(
    r"(?:^|\b)(?:please\s+)?(?:start|begin|create)\s+(?:a\s+)?"
    r"(?:(?:new|another|separate|unrelated)\s+)?(?:task|job|run|piece\s+of\s+work)\b|"
    r"\b(?:new|another|separate|unrelated)\s+(?:task|job|piece\s+of\s+work)\b",
    re.IGNORECASE,
)
_SPOKEN_CURSOR_REFERENCE = re.compile(
    r"\b(?:look\s+at|open|show|inspect|fix|change|review|click|press|select|use|read|do)\s+"
    r"(?:this|that)\b|"
    r"\b(?:this|that)\s+(?:button|window|file|selection|thing|control|object|area|part|one)\b|"
    r"\b(?:what(?:'s|\s+is))\s+(?:this|that)\b|"
    r"\bover\s+here\b",
    re.IGNORECASE,
)


def classify_voice_intent(text: str) -> VoiceConversationIntent:
    """Classify only explicit control language; ordinary speech stays dialogue."""

    if _STOP_SPEAKING.fullmatch(text):
        return VoiceConversationIntent.STOP_SPEAKING
    if _CANCEL_TASK.search(text):
        return VoiceConversationIntent.CANCEL_TASK
    if _STEER_TASK.search(text):
        return VoiceConversationIntent.STEER_TASK
    if _NEW_WORK.search(text):
        return VoiceConversationIntent.NEW_WORK
    return VoiceConversationIntent.DIALOGUE


def contains_spoken_cursor_reference(text: str) -> bool:
    """Return whether resolving the utterance requires historical cursor position."""

    return _SPOKEN_CURSOR_REFERENCE.search(text) is not None


def new_work_description(text: str) -> str:
    """Keep the full spoken request while removing only a conventional control prefix."""

    stripped = text.strip()
    match = re.match(
        r"^(?:please\s+)?(?:start|begin|create)\s+(?:a\s+)?"
        r"(?:(?:new|another|separate|unrelated)\s+)?(?:task|job|run|piece\s+of\s+work)"
        r"(?:\s+(?:to|for))?\s*[:,-]?\s*(.*)$",
        stripped,
        re.IGNORECASE,
    )
    if match is not None and match.group(1).strip():
        return match.group(1).strip()
    return stripped
