"""Transient request-scoped conversation cancellation, including admission/commit races."""

from __future__ import annotations

import asyncio
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sora.providers.dialogue import DialogueProviderError, DialogueTimeoutError


class DialogueCancelledError(DialogueProviderError):
    """A stopped or invalidated conversation turn must not publish a late result."""


class DialogueRequestConflict(ValueError):
    pass


@dataclass
class DialogueTurn:
    request_id: str
    local: bool
    task: asyncio.Task[str] | None = None
    phase: str = "running"
    cancel_reason: str | None = None
    expires_at: float | None = None

    def check(self) -> None:
        if self.cancel_reason is not None:
            raise DialogueCancelledError("Response stopped; retry with a new request.")
        if self.expires_at is not None and time.monotonic() >= self.expires_at:
            raise DialogueTimeoutError("The conversation deadline was reached")

    def begin_commit(self) -> None:
        self.check()
        self.phase = "committing"  # No await between check and the commit boundary.


class DialogueTurns:
    def __init__(self) -> None:
        self.active: dict[tuple[bool, str], DialogueTurn] = {}
        self._recent: OrderedDict[tuple[bool, str], tuple[str, float]] = OrderedDict()
        self._closed = False

    @staticmethod
    def validate_id(value: str | None) -> str:
        if value is None:
            return uuid.uuid4().hex
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
            raise ValueError("Invalid conversation request ID")
        return value

    def _retire(self, key: tuple[bool, str], state: str) -> None:
        self._recent[key] = state, time.monotonic()
        self._recent.move_to_end(key)
        while len(self._recent) > 256:
            self._recent.popitem(last=False)

    def _prune(self) -> None:
        now = time.monotonic()
        while self._recent and now - next(iter(self._recent.values()))[1] > 600:
            self._recent.popitem(last=False)

    @property
    def count(self) -> int:
        return len(self.active)

    async def run(
        self,
        operation: Callable[[DialogueTurn], Awaitable[str]],
        *,
        request_id: str | None,
        local: bool,
    ) -> str:
        if self._closed:
            raise DialogueProviderError("Core is stopping; retry after restart")
        key = local, self.validate_id(request_id)
        self._prune()
        if key in self.active:
            raise DialogueRequestConflict("Conversation request is already running")
        if key in self._recent:
            if self._recent[key][0] == "cancelled-before-start":
                raise DialogueCancelledError("Response stopped before it started")
            raise DialogueRequestConflict("Use a new conversation request ID")
        turn = DialogueTurn(key[1], local)

        async def invoke() -> str:
            try:
                result = await operation(turn)
                turn.check()
                turn.phase = "completed"
                return result
            except asyncio.CancelledError:
                turn.phase = "cancelled"
                if turn.cancel_reason:
                    raise DialogueCancelledError("Response stopped; retry when ready") from None
                raise
            except DialogueCancelledError:
                turn.phase = "cancelled"
                raise
            except Exception:
                turn.phase = "failed"
                raise
            finally:
                self.active.pop(key, None)
                self._retire(key, turn.phase)

        turn.task = asyncio.create_task(invoke(), name="sora-conversation-turn")
        self.active[key] = turn
        try:
            return await turn.task
        except asyncio.CancelledError:
            if turn.cancel_reason:
                raise DialogueCancelledError("Response stopped before generation") from None
            raise
        finally:
            # A Task cancelled before invoke's first instruction never enters its finally.
            if self.active.get(key) is turn:
                self.active.pop(key)
                self._retire(key, "cancelled" if turn.cancel_reason else "failed")

    def cancel(self, request_id: str, *, local: bool, reason: str = "user") -> str:
        key = local, self.validate_id(request_id)
        self._prune()
        turn = self.active.get(key)
        if turn is None:
            if key in self._recent:
                return self._recent[key][0]
            # Stop can overtake POST on separate connections. This bounded tombstone stops
            # only that exact nonce, never another client or the next generated request.
            self._retire(key, "cancelled-before-start")
            return "cancelled-before-start"
        if turn.phase in {"committing", "committed"}:
            return "already-finishing"
        turn.cancel_reason = reason
        if turn.task is not None and turn.task is not asyncio.current_task():
            turn.task.cancel()
        return "cancelling"

    def invalidate_local(self, reason: str) -> None:
        for local, request_id in tuple(self.active):
            if local:
                self.cancel(request_id, local=local, reason=reason)

    async def close(self) -> None:
        self._closed = True
        tasks = [turn.task for turn in self.active.values() if turn.task is not None]
        for turn in tuple(self.active.values()):
            self.cancel(turn.request_id, local=turn.local, reason="shutdown")
        if tasks:
            done, _ = await asyncio.wait(tasks, timeout=2)
            # Observe exceptions even if the HTTP caller was disconnected during shutdown.
            for task in done:
                if not task.cancelled():
                    task.exception()
