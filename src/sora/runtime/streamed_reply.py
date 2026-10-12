"""The model's free-text reply, optionally streamed to a listener as it is written.

Voice turns pass a listener so SORA can start speaking the first sentence while the model is
still writing the rest. The turn's committed reply is the same text either way.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from sora.contracts.models import ActiveCapabilitySet
from sora.providers.dialogue import (
    DialogueProvider,
    DialogueProviderError,
    ImageDialogueProvider,
    StreamingReplyProvider,
)

type ReplyListener = Callable[[str], None]


async def write_reply(
    provider: DialogueProvider,
    text: str,
    context: str,
    images: tuple[str, ...] = (),
    *,
    active: ActiveCapabilitySet | None,
    source: Literal["owner", "screen"] = "owner",
    on_text: ReplyListener | None = None,
) -> str:
    if on_text is not None and isinstance(provider, StreamingReplyProvider):
        parts: list[str] = []
        async for delta in provider.stream_reply(text, context, images, source=source):
            parts.append(delta)
            on_text(delta)
        reply = "".join(parts).strip()
        if not reply:
            raise DialogueProviderError("Direct dialogue provider returned invalid text")
        return reply
    if images:
        assert isinstance(provider, ImageDialogueProvider)
        return await provider.respond_with_images(
            text, context, images, active_capabilities=active, source=source,
        )
    return await provider.respond(text, context, active_capabilities=active)
