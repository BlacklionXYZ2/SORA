"""P10.7 validated handler selection and shell-free process launch."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sora.contracts.content import ContentHandlerConfig, ContentReference


class ContentNavigationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PreparedContentNavigation:
    reference: ContentReference
    handler: ContentHandlerConfig
    argv: tuple[str, ...]
    limitations: tuple[str, ...]


class ContentNavigator:
    """Validates configured roots/handlers and launches without a command shell."""

    def __init__(
        self,
        *,
        roots: tuple[Path, ...] = (),
        handlers: tuple[ContentHandlerConfig, ...] = (),
    ) -> None:
        canonical_roots: dict[str, Path] = {}
        for root in roots:
            resolved = root.resolve(strict=True)
            if not resolved.is_dir():
                raise ValueError(f"content root must be a directory: {root}")
            canonical_roots[str(resolved).casefold()] = resolved
        self.roots = tuple(canonical_roots.values())
        self.handlers = {handler.handler_id: handler for handler in handlers}
        if len(self.handlers) != len(handlers):
            raise ValueError("content handler IDs must be unique")
        for handler in handlers:
            if not handler.executable.resolve(strict=True).is_file():
                raise ValueError(f"content handler executable must be a file: {handler.executable}")

    def validate_reference(self, reference: ContentReference) -> ContentReference:
        if not self.roots or str(reference.root.resolve(strict=False)).casefold() not in {
            str(root).casefold() for root in self.roots
        }:
            raise ContentNavigationError("root_not_configured", "content root is not configured")
        try:
            root = reference.root.resolve(strict=True)
            path = reference.path.resolve(strict=True)
        except OSError as exc:
            raise ContentNavigationError(
                "content_unavailable", "content path is unavailable"
            ) from exc
        if not path.is_relative_to(root):
            raise ContentNavigationError("path_outside_root", "content path escapes its root")
        if reference.kind == "repository":
            if not path.is_dir():
                raise ContentNavigationError(
                    "content_unavailable", "repository path is not a directory"
                )
        elif not path.is_file():
            raise ContentNavigationError("content_unavailable", "content path is not a file")
        return reference.model_copy(update={"root": root, "path": path})

    def prepare(
        self,
        reference: ContentReference,
        *,
        verb: str,
        line: int | None = None,
        column: int | None = None,
    ) -> PreparedContentNavigation:
        reference = self.validate_reference(reference)
        handler = self._handler(reference)
        if verb not in handler.verbs:
            raise ContentNavigationError(
                "verb_unsupported",
                f"handler '{handler.handler_id}' does not support '{verb}'",
            )
        effective_line = line if line is not None else reference.line
        effective_column = column if column is not None else reference.column
        limitations: list[str] = []
        if effective_line is not None and not handler.supports_line:
            limitations.append(
                "handler cannot navigate to a line; opened the content without line targeting"
            )
            effective_line = None
            effective_column = None
        elif effective_column is not None and not handler.supports_column:
            limitations.append("handler cannot navigate to a column; opened the requested line")
            effective_column = None
        if verb == "where" and not handler.supports_highlight:
            limitations.append("handler cannot highlight the content location")

        values = {
            "path": str(reference.path),
            "line": str(effective_line or ""),
            "column": str(effective_column or ""),
            "reference_id": reference.reference_id,
            "verb": verb,
        }
        try:
            arguments = tuple(argument.format_map(values) for argument in handler.arguments)
        except (KeyError, ValueError) as exc:
            raise ContentNavigationError(
                "invalid_handler_arguments", "handler argument expansion failed"
            ) from exc
        return PreparedContentNavigation(
            reference=reference,
            handler=handler,
            argv=(str(handler.executable.resolve(strict=True)), *arguments),
            limitations=tuple(limitations),
        )

    def _handler(self, reference: ContentReference) -> ContentHandlerConfig:
        if reference.handler_id is not None:
            handler = self.handlers.get(reference.handler_id)
            if handler is None:
                raise ContentNavigationError(
                    "handler_not_configured", "requested content handler is not configured"
                )
            if reference.kind not in handler.kinds:
                raise ContentNavigationError(
                    "kind_unsupported", "requested handler does not support this content kind"
                )
            return handler
        matches = tuple(
            handler for handler in self.handlers.values() if reference.kind in handler.kinds
        )
        if not matches:
            raise ContentNavigationError(
                "handler_not_configured", "no configured handler supports this content kind"
            )
        if len(matches) > 1:
            raise ContentNavigationError(
                "handler_ambiguous", "multiple handlers support this content kind"
            )
        return matches[0]

    async def launch(self, prepared: PreparedContentNavigation) -> tuple[int, int | None]:
        try:
            process = await asyncio.create_subprocess_exec(
                *prepared.argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            raise ContentNavigationError(
                "launch_failed", "configured handler could not start"
            ) from exc
        timeout = prepared.handler.completion_timeout_seconds
        if timeout > 0:
            try:
                exit_code = await asyncio.wait_for(process.wait(), timeout=timeout)
            except TimeoutError:
                return process.pid, None
            if exit_code != 0:
                raise ContentNavigationError(
                    "handler_failed", f"configured handler exited with code {exit_code}"
                )
            return process.pid, exit_code
        await asyncio.sleep(0.05)
        if process.returncode not in (None, 0):
            raise ContentNavigationError(
                "handler_failed", f"configured handler exited with code {process.returncode}"
            )
        return process.pid, process.returncode
