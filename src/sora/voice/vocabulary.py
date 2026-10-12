"""Names the speech recogniser should expect: her wake word and her agent colleagues.

Whisper hears unfamiliar names as ordinary words ("Claude" as "cloud", "Sora" as "Sarah"), and
then neither the window nor the agent the owner named can be matched. faster-whisper's
``hotwords`` biases recognition toward a short list of phrases. Core sends the agents' names
(including custom agents' nicknames) to the voice worker when it starts; the worker adds the
wake word first.
"""

from __future__ import annotations

from collections.abc import Iterable

MAX_NAMES = 12
MAX_CHARS = 160


def clean_names(names: Iterable[object]) -> tuple[str, ...]:
    """Distinct, short, printable names; anything else from the pipe is dropped."""
    kept: list[str] = []
    seen: set[str] = set()
    for item in names:
        if not isinstance(item, str):
            continue
        name = " ".join(item.split())
        if not name or len(name) > 40 or not name.isprintable() or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        kept.append(name)
        if len(kept) == MAX_NAMES:
            break
    return tuple(kept)


def hotwords(wake_words: str, names: Iterable[object] = ()) -> str | None:
    """The hotword string: the first wake word, then the names, bounded in count and length."""
    wake = wake_words.split(",")[0].strip().title()
    words = clean_names(([wake] if wake else []) + list(names))
    text = ""
    for word in words:
        candidate = f"{text}, {word}" if text else word
        if len(candidate) > MAX_CHARS:
            break
        text = candidate
    return text or None
