"""Reasoning-provider interfaces and verified concrete adapters."""

from .antigravity import AntigravityProvider, parse_antigravity_result
from .base import OwnedWorkspaceProvider, ReasoningProvider
from .claude_code import ClaudeCodeProvider, parse_claude_result
from .codex import CodexAppServerProvider, parse_codex_result
from .dialogue import (
    DeterministicDialogueProvider,
    DialogueProvider,
    DialogueProviderError,
    OpenAICompatibleDialogueProvider,
)
from .hermes import HermesACPProvider, parse_hermes_result

__all__ = [
    "AntigravityProvider",
    "ClaudeCodeProvider",
    "CodexAppServerProvider",
    "DeterministicDialogueProvider",
    "DialogueProvider",
    "DialogueProviderError",
    "OpenAICompatibleDialogueProvider",
    "HermesACPProvider",
    "OwnedWorkspaceProvider",
    "ReasoningProvider",
    "parse_antigravity_result",
    "parse_claude_result",
    "parse_codex_result",
    "parse_hermes_result",
]
