"""Storing a moment SORA chose to remember with the ``remember`` tool.

The memory row holds her description (a lasting fact, complete on its own) and title; the turn
entry (sora.memory.entries) holds the owner's exact words, her reply, what was read, the images
and the owner's voice. The memory manager later embeds each part and keeps the relevant ones.

This replaces the older after-every-turn "remember? yes/no" call for brains that use companion
calls; that call remains for other brains.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from sora.contracts.companion_call import Remember
from sora.memory.entries import ImageSource, write_entry
from sora.memory.features import words
from sora.persistence.repository import SoraRepository

if TYPE_CHECKING:
    from sora.providers.dialogue import DialogueProvider
    from sora.runtime.read_turn import ReadTurn


@dataclass(frozen=True)
class TurnMoment:
    """Everything a remembered turn keeps, gathered once after the reply is committed."""

    text: str
    reply: str
    images: tuple[str, ...]
    owner_images: tuple[str, ...]
    provider: DialogueProvider
    message_id: str
    read_turn: ReadTurn | None
    application: str

# How the owner tells her to behave from now on. A small model rarely sets the optional
# ``standing`` flag (live, 2026-10-10), so the owner's own words decide it too.
_STANDING = re.compile(
    r"\b(from now on|going forward|in future|from today)\b"
    r"|\b(always|never)\b.{0,40}\b(you|your|answer|reply|replies|talk|speak|say|call)\b"
    r"|\b(call me|don'?t (talk|speak|interrupt)|stop (talking|saying|calling))\b",
    re.IGNORECASE,
)


# A "thought" that only reports a fact about the owner ("The user has instructed me to keep
# answers short") belongs to the owner's memories, not hers (live, 2026-10-10).
ABOUT_OWNER = re.compile(r"\bthe (user|owner)\b|\b(user|owner)'s\b", re.IGNORECASE)


def echoes(thought: str, owner_text: str) -> bool:
    """Her "thought" mostly repeats the owner's words ("I like lo-fi music when I code.")."""
    mine, theirs = words(thought), words(owner_text)
    return bool(mine) and len(mine & theirs) / len(mine) >= 0.6


def is_standing(remember: Remember, owner_text: str) -> bool:
    return remember.standing or bool(_STANDING.search(owner_text))


async def remember_turn(
    repository: SoraRepository, remember: Remember, *, entries: Path, owner_id: str,
    project_id: str | None, owner_text: str, reply: str, read_observations: str,
    images: Sequence[tuple[str, ImageSource]], audio_wav_base64: str | None,
    provider: str, context: Mapping[str, str],
) -> tuple[str, int] | None:
    """Write the entry and the memory. Returns (memory_id, media files) or None for a repeat."""
    title = " ".join(remember.title.split())
    description = " ".join(remember.description.split())
    now = datetime.now(UTC)
    existing = await repository.list_memories(owner_id, project_id=project_id, observed_at=now)
    if any(m.content.casefold() == description.casefold() for m in existing):
        return None  # already remembered in these words
    memory_id = f"memory-{uuid.uuid4()}"
    media = 0
    try:
        entry = write_entry(
            entries, memory_id=memory_id, created_at=now, title=title, description=description,
            owner_text=owner_text, reply=reply, read_observations=read_observations,
            images=images, audio_wav_base64=audio_wav_base64,
            context={**context, "decided_by": "remember tool", "provider": provider})
        media = len(entry.media)
    except OSError:
        pass  # the memory itself still counts; its turn data is lost
    await repository.add_memory(
        memory_id=memory_id, owner_id=owner_id, project_id=project_id, content=description,
        title=title, scope="standing" if is_standing(remember, owner_text) else "dialogue",
        sensitivity="private", retention="durable",
        provenance=f"owner-stated (remember tool via {provider})")
    return memory_id, media
