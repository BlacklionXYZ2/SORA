"""Reasoning-provider interfaces and verified concrete adapters."""

from .antigravity import AntigravityProvider, parse_antigravity_result
from .base import ReasoningProvider
from .codex import CodexAppServerProvider, parse_codex_result
from .dialogue import DeterministicDialogueProvider, DialogueProvider
from .hermes import HermesACPProvider, parse_hermes_result

__all__ = [
    "AntigravityProvider",
    "CodexAppServerProvider",
    "DeterministicDialogueProvider",
    "DialogueProvider",
    "HermesACPProvider",
    "ReasoningProvider",
    "parse_antigravity_result",
    "parse_codex_result",
    "parse_hermes_result",
]

