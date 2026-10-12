"""Automatic screen captures must not read as something the owner sent (owner report)."""

from __future__ import annotations

from sora.providers.dialogue import SCREEN_IMAGE_NOTE, OpenAICompatibleDialogueProvider

IMAGE = "data:image/png;base64,AAAA"


def _texts(messages: list[dict[str, object]]) -> list[str]:
    content = messages[-1]["content"]
    assert isinstance(content, list)
    return [part["text"] for part in content if part.get("type") == "text"]


def test_screen_capture_is_labelled_as_sora_own_view() -> None:
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1/v1", model="m")
    messages = provider._build_messages("What's this?", "context", (IMAGE,), "screen")
    texts = _texts(messages)
    assert texts == ["What's this?", SCREEN_IMAGE_NOTE]
    assert "screen or the desktop" in SCREEN_IMAGE_NOTE
    assert "did not send" in SCREEN_IMAGE_NOTE


def test_owner_attachment_is_not_relabelled() -> None:
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1/v1", model="m")
    messages = provider._build_messages("What's this?", "context", (IMAGE,))
    assert _texts(messages) == ["What's this?"]
