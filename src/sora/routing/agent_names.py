"""What SORA calls her agent colleagues, and the spoken forms that reach each one.

One table serves typed and spoken text, steering, cancellation and result presentation, so a
name means the same agent everywhere. Keys are the routing/registry keys (``codex``, ``hermes``,
``antigravity``, ``claude``, ``custom-1``…). Provider IDs are the adapters'
``ProviderCapabilities.provider`` values, which task records may carry instead of the key.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

CUSTOM_SLOTS = ("custom-1", "custom-2", "custom-3", "custom-4")
_ALIAS = re.compile(r"^[a-z0-9][a-z0-9' -]{0,38}[a-z0-9]$|^[a-z0-9]$")


@dataclass(frozen=True, slots=True)
class AgentName:
    key: str
    name: str
    provider_ids: tuple[str, ...]
    aliases: tuple[str, ...]
    pattern: re.Pattern[str] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        forms = sorted({normalise_alias(item) for item in (self.name, *self.aliases)},
                       key=len, reverse=True)
        # Spoken forms may arrive spaced, hyphenated or joined ("anti gravity", "antigravity").
        body = "|".join(r"[\s_-]*".join(map(re.escape, form.split())) for form in forms)
        object.__setattr__(
            self, "pattern", re.compile(rf"(?<![\w])(?:{body})(?![\w])", re.IGNORECASE),
        )

    def owns(self, backend: str | None) -> bool:
        return backend is not None and (backend == self.key or backend in self.provider_ids)


def normalise_alias(value: str) -> str:
    return " ".join(value.casefold().replace("-", " ").replace("_", " ").split())


def parse_aliases(text: str) -> tuple[str, ...]:
    """Comma-separated owner input to unique normalised aliases; invalid entries raise."""
    result: list[str] = []
    for raw in text.split(","):
        alias = normalise_alias(raw)
        if not alias:
            continue
        if not _ALIAS.match(alias):
            raise ValueError(f"Spoken alias '{raw.strip()}' must be 1-40 letters, digits or spaces")
        if alias not in result:
            result.append(alias)
    return tuple(result)


# Spoken variants are what speech-to-text commonly produces for each name. Short or common
# English words ("cloud", "code") are deliberately absent: they would capture ordinary speech.
BUILTIN_AGENTS = (
    AgentName("codex", "Cody", ("codex-app-server",),
              ("cody", "codey", "codie", "kody", "kodi", "codex", "code x")),
    AgentName("hermes", "Hermes", ("hermes-acp",), ("hermes", "hermies", "her mees")),
    AgentName("antigravity", "Aggie", ("antigravity",),
              ("aggie", "aggy", "aggi", "agy", "ag", "antigravity", "anti gravity")),
    AgentName("claude", "Claude", ("claude-code",), ("claude", "claud", "klaud", "clawed")),
)

_REQUEST_VERBS = (
    r"(?:ask|have|get|use|let|tell|delegate(?:\s+(?:it|this|that))?\s+to|"
    r"(?:hand|give|pass|send)\s+(?:it|this|that)\s+(?:over\s+)?to)"
)


class AgentDirectory:
    """Immutable lookup over built-in colleagues plus the owner's named custom endpoints."""

    def __init__(self, agents: Iterable[AgentName] = BUILTIN_AGENTS) -> None:
        self.agents = tuple(agents)
        seen: dict[str, str] = {}
        for agent in self.agents:
            for form in {normalise_alias(item) for item in (agent.name, *agent.aliases)}:
                owner = seen.setdefault(form, agent.key)
                if owner != agent.key:
                    raise ValueError(f"'{form}' already names another agent")
        self._by_key = {agent.key: agent for agent in self.agents}

    def with_custom(self, endpoints: Sequence[tuple[str, str, Sequence[str]]]) -> AgentDirectory:
        """Add ``(key, nickname, aliases)`` custom endpoints; name clashes raise ValueError."""
        extra = [AgentName(key, nickname, (key,), tuple(aliases))
                 for key, nickname, aliases in endpoints]
        return AgentDirectory((*self.agents, *extra))

    def get(self, key: str) -> AgentName | None:
        return self._by_key.get(key)

    def for_backend(self, backend: str | None) -> AgentName | None:
        return next((agent for agent in self.agents if agent.owns(backend)), None)

    def name_for(self, backend: str | None, default: str | None = None) -> str | None:
        agent = self.for_backend(backend)
        return agent.name if agent is not None else default

    def resolve(self, text: str) -> str | None:
        """Exact key, name or alias to its key."""
        wanted = normalise_alias(text)
        for agent in self.agents:
            forms = {normalise_alias(item) for item in (agent.key, agent.name, *agent.aliases)}
            if wanted in forms:
                return agent.key
        return None

    def mentioned(self, text: str) -> tuple[str, ...]:
        """Keys of every agent named anywhere in ``text``, in order of first mention."""
        found = sorted(
            (match.start(), agent.key)
            for agent in self.agents
            if (match := agent.pattern.search(text)) is not None
        )
        return tuple(dict.fromkeys(key for _, key in found))

    def requested(self, text: str) -> tuple[str, ...]:
        """Agents the owner explicitly asks for ("ask Cody", "hand it to Aggie")."""
        found: list[tuple[int, str]] = []
        for agent in self.agents:
            body = agent.pattern.pattern.removeprefix(r"(?<![\w])")
            match = re.search(rf"\b{_REQUEST_VERBS}\s+{body}", text, re.IGNORECASE)
            if match is not None:
                found.append((match.start(), agent.key))
        return tuple(dict.fromkeys(key for _, key in sorted(found)))

    def describe(self) -> list[dict[str, Any]]:
        return [{"key": agent.key, "name": agent.name, "aliases": list(agent.aliases)}
                for agent in self.agents]


DEFAULT_DIRECTORY = AgentDirectory()
