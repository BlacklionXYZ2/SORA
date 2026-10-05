"""Reliable cooperating-editor context handoff."""

from .context import EditorContextError, resolve_editor_context

__all__ = ["EditorContextError", "resolve_editor_context"]
