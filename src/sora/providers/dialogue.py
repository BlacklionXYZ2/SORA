"""Direct dialogue provider protocol and deterministic implementation."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from sora.contracts.models import ActiveCapabilitySet


class DialogueProvider(Protocol):
    """Interface for direct fast conversational model providers."""

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]: ...

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str: ...


class DeterministicDialogueProvider:
    """Mock dialogue provider for responsive conversation and delegation acknowledgment."""

    def __init__(self, delay_seconds: float = 0.0) -> None:
        self.delay_seconds = delay_seconds

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        full_text = await self.respond(
            prompt, context, active_capabilities=active_capabilities
        )
        words = full_text.split(" ")
        for index, word in enumerate(words):
            if self.delay_seconds > 0:
                await asyncio.sleep(self.delay_seconds)
            suffix = " " if index < len(words) - 1 else ""
            yield word + suffix

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        prompt_lower = prompt.lower()
        if "cody" in prompt_lower or "code" in prompt_lower or "fix" in prompt_lower:
            return "I'll ask Cody to take a look at that."
        if "hermes" in prompt_lower or "research" in prompt_lower:
            return "I'll get Hermes to investigate that for you."
        if "pause" in prompt_lower:
            return "Pausing playback for you."
        if "board" in prompt_lower or "kanban" in prompt_lower:
            return "I'll put that on the board."
        return f"SORA is available while background tasks run. You said: {prompt.strip()}"

