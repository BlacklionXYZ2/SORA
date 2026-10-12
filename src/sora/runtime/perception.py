"""Transient prompt-time perception; never a source of action authority."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import math
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field, StrictBool

from sora.contracts.base import StrictModel
from sora.contracts.capture import DesktopCaptureSource, DesktopCaptureStatus
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.desktop.capture import WindowsCaptureBridge, WindowsCaptureRequest
from sora.desktop.foreground import ForegroundIdentity
from sora.vision.capture import validate_png_dimensions


class PerceptionSettings(StrictModel):
    # V1 sends the current window with every text and voice prompt (V1.md step 4). Settings
    # migrated from before perception existed keep native-only; see AppSettingsStore.load.
    mode: Literal["native-only", "image-on-prompt", "adaptive"] = "image-on-prompt"
    paused: StrictBool = False
    window_context: StrictBool = True
    desktop_context: StrictBool = True
    interval_seconds: float = Field(default=30, ge=5, le=300)
    context_max_age_seconds: float = Field(default=90, ge=5, le=600)


@dataclass(frozen=True)
class PromptImage:
    capture_id: str
    captured_at: datetime
    data_url: str
    sha256: str


@dataclass(frozen=True)
class PerceptionSample:
    identity: ForegroundIdentity
    image: PromptImage


@dataclass(frozen=True)
class AmbientContext:
    identity: ForegroundIdentity
    captured_at: datetime
    verified_at: datetime
    summary: str
    sha256: str


def application_key(identity: ForegroundIdentity) -> tuple[int, int, datetime]:
    return identity.process_id, identity.window_handle, identity.process_started_at


class PerceptionBusyError(ValueError):
    """A cancelled background request has not yet released its model transport."""


class AdaptivePerception:
    """One replaceable background refresh; foreground work preempts, never queues behind it."""

    def __init__(
        self, *, enabled: Callable[[], bool], interval: Callable[[], float],
        sample: Callable[[], Awaitable[PerceptionSample | None]],
        interpret: Callable[[PromptImage], Awaitable[str]],
    ) -> None:
        self.enabled = enabled
        self.interval = interval
        self.sample = sample
        self.interpret = interpret
        self.context: AmbientContext | None = None
        self.state = "disabled"
        self.interpretations = 0
        self.unchanged = 0
        self.last_duration_seconds: float | None = None
        self._generation = 0
        self._foreground = 0
        self._closed = False
        self._wake = asyncio.Event()
        self._runner: asyncio.Task[None] | None = None
        self._refresh: asyncio.Task[object] | None = None

    def invalidate(self) -> None:
        self._generation += 1
        self.context = None
        if self._refresh is not None and not self._refresh.done():
            self._refresh.cancel()
        self._wake.set()

    def start(self) -> None:
        if self._runner is None or self._runner.done():
            self._closed = False
            self._runner = asyncio.create_task(self._run(), name="adaptive-perception")

    async def stop(self) -> None:
        self._closed = True
        self.invalidate()
        if self._runner is not None:
            self._runner.cancel()
            await asyncio.gather(self._runner, return_exceptions=True)
            self._runner = None
        if self._refresh is not None:
            await asyncio.gather(self._refresh, return_exceptions=True)
        self.state = "disabled"

    @asynccontextmanager
    async def foreground(self) -> AsyncIterator[None]:
        self._foreground += 1  # Close background admission before the first await.
        try:
            refresh = self._refresh
            if refresh is not None and not refresh.done():
                self._generation += 1  # Late cancellation acknowledgement cannot publish.
                refresh.cancel()
                done, _ = await asyncio.wait({refresh}, timeout=2)
                if not done:
                    raise PerceptionBusyError("Background model cancellation is pending; retry")
            yield
        finally:
            self._foreground -= 1
            self._wake.set()

    def recent(
        self, identity: ForegroundIdentity | None, max_age: float,
        *, now: datetime | None = None,
    ) -> AmbientContext | None:
        context = self.context
        if context is None or identity is None:
            return None
        age = ((now or datetime.now(UTC)) - context.verified_at).total_seconds()
        if (application_key(identity) != application_key(context.identity)
                or not 0 <= age <= max_age):
            return None
        return context

    async def refresh_once(self) -> bool:
        task = asyncio.current_task()
        assert task is not None
        if self._closed or self._foreground or not self.enabled() or self._refresh is not None:
            return False
        self._refresh = task
        generation = self._generation
        started = asyncio.get_running_loop().time()

        def check() -> None:
            if (generation != self._generation or self._foreground or self._closed
                    or not self.enabled()):
                raise asyncio.CancelledError

        try:
            self.state = "capturing"
            sample = await self.sample()
            check()
            if sample is None:
                self.context = None
                self.state = "no-recent-application"
                return False
            old = self.context
            if (old is not None
                    and application_key(old.identity) == application_key(sample.identity)
                    and old.sha256 == sample.image.sha256):
                self.context = AmbientContext(
                    sample.identity, old.captured_at, sample.image.captured_at,
                    old.summary, old.sha256,
                )
                self.unchanged += 1
                self.state = "unchanged"
                return True
            self.state = "interpreting"
            self.context = None
            summary = await self.interpret(sample.image)
            check()
            self.context = AmbientContext(
                sample.identity, sample.image.captured_at, sample.image.captured_at,
                summary.strip()[:1600], sample.image.sha256,
            )
            self.interpretations += 1
            self.state = "ready"
            return True
        except asyncio.CancelledError:
            self.state = "waiting-for-conversation" if self._foreground else "invalidated"
            raise
        except Exception:
            # Backend errors may contain private prompts/paths; expose only bounded state.
            self.context = None
            self.state = "unavailable"
            return False
        finally:
            self.last_duration_seconds = round(asyncio.get_running_loop().time() - started, 3)
            self._refresh = None

    async def _run(self) -> None:
        period = self.interval()
        due = asyncio.get_running_loop().time() + period
        try:
            while not self._closed:
                self._wake.clear()
                now = asyncio.get_running_loop().time()
                new_period = self.interval()
                if new_period != period:
                    period = new_period
                    due = now + period
                if now >= due:
                    if self._foreground:
                        self.state = "waiting-for-conversation"
                    elif self.enabled():
                        # Child cancellation yields the slot without terminating the timer.
                        refresh = asyncio.create_task(self.refresh_once())
                        try:
                            await refresh
                        except asyncio.CancelledError:
                            if self._closed:
                                raise
                    else:
                        self.context = None
                        self.state = "disabled"
                    period = self.interval()
                    due = asyncio.get_running_loop().time() + period
                try:
                    await asyncio.wait_for(
                        self._wake.wait(), max(0.01, due - asyncio.get_running_loop().time())
                    )
                except TimeoutError:
                    pass
        finally:
            self.context = None


async def capture_application(
    identity: ForegroundIdentity,
    bridge: WindowsCaptureBridge,
    check: Callable[[], None],
) -> PromptImage:
    """Capture only the validated application identity; no display/focus fallback or storage."""
    check()
    started = datetime.now(UTC)
    request = WindowsCaptureRequest(
        capture_id=f"perception-{uuid.uuid4()}",
        source=DesktopCaptureSource.WINDOW,
        process_id=identity.process_id,
        window_handle=identity.window_handle,
        process_started_at=identity.process_started_at,
    )
    reply = await bridge.capture(request)
    check()
    if reply.status is not DesktopCaptureStatus.OK:
        raise ValueError(f"Window image unavailable ({reply.status.value})")
    if (reply.process_id, reply.window_handle, reply.process_started_at) != (
        identity.process_id,
        identity.window_handle,
        identity.process_started_at,
    ):
        raise ValueError("Window identity changed during capture")
    if reply.captured_at is None or not started - timedelta(seconds=1) <= (
        reply.captured_at
    ) <= datetime.now(UTC) + timedelta(seconds=1):
        raise ValueError("Window image timestamp is invalid")
    assert reply.region is not None
    if reply.region.width * reply.region.height > request.max_pixels:
        raise ValueError("Window image exceeds the pixel budget")
    raw = base64.b64decode(reply.png_base64, validate=True)
    if len(raw) > request.max_bytes:
        raise ValueError("Window image exceeds the byte budget")
    validate_png_dimensions(raw, reply.region.width, reply.region.height)
    check()
    return PromptImage(
        capture_id=request.capture_id,
        captured_at=reply.captured_at,
        data_url="data:image/png;base64," + reply.png_base64,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


OVERVIEW_MAX_EDGE = 1920  # when the model's image token budget is unknown (external servers)
PIXELS_PER_IMAGE_TOKEN = 2304  # Gemma 4: one image token covers about 48x48 source pixels


def overview_edge(bounds: ScreenRect, image_tokens: int) -> int:
    """The longest edge at which the overview just fills the model's image token budget.

    A larger image is scaled down again by llama.cpp, so capturing more only costs time.
    """
    pixels = image_tokens * PIXELS_PER_IMAGE_TOKEN
    long_side, short_side = max(bounds.width, bounds.height), min(bounds.width, bounds.height)
    edge = math.isqrt(pixels * long_side // short_side)  # rounded down: stay within budget
    return max(256, min(4096, long_side, edge))


@dataclass(frozen=True)
class DesktopOverview:
    image: PromptImage
    layout: str  # where each monitor sits in the image, for the model


def desktop_bounds(monitors: tuple[MonitorDescriptor, ...]) -> ScreenRect:
    left = min(monitor.rect.x for monitor in monitors)
    top = min(monitor.rect.y for monitor in monitors)
    right = max(monitor.rect.x + monitor.rect.width for monitor in monitors)
    bottom = max(monitor.rect.y + monitor.rect.height for monitor in monitors)
    return ScreenRect(x=left, y=top, width=right - left, height=bottom - top)


def describe_layout(monitors: tuple[MonitorDescriptor, ...], bounds: ScreenRect) -> str:
    """Say where each monitor sits in the overview, so the model can tell the screens apart."""
    parts = []
    for monitor in sorted(monitors, key=lambda item: (item.rect.x, item.rect.y)):
        start = round(100 * (monitor.rect.x - bounds.x) / bounds.width)
        end = round(100 * (monitor.rect.x + monitor.rect.width - bounds.x) / bounds.width)
        parts.append(
            f"{'primary' if monitor.primary else 'secondary'} monitor "
            f"{monitor.rect.width}x{monitor.rect.height} ({start}-{end}% of the width)"
        )
    if len(monitors) == 1:
        return "1 monitor: " + parts[0]
    return (
        f"{len(monitors)} monitors, left to right: " + ", ".join(parts)
        + "; black areas are outside every monitor"
    )


async def capture_desktop_overview(
    monitors: tuple[MonitorDescriptor, ...],
    bridge: WindowsCaptureBridge,
    check: Callable[[], None],
    *,
    max_edge: int = OVERVIEW_MAX_EDGE,
) -> DesktopOverview:
    """Capture every monitor as one reduced image; nothing is stored."""
    check()
    bounds = desktop_bounds(monitors)
    started = datetime.now(UTC)
    request = WindowsCaptureRequest(
        capture_id=f"overview-{uuid.uuid4()}",
        source=DesktopCaptureSource.REGION,
        region=bounds,
        output_max_edge=max_edge,
    )
    reply = await bridge.capture(request)
    check()
    if reply.status is not DesktopCaptureStatus.OK:
        raise ValueError(f"Desktop image unavailable ({reply.status.value})")
    if reply.region != bounds or reply.image_width is None or reply.image_height is None:
        raise ValueError("Desktop image does not match the requested monitors")
    if max(reply.image_width, reply.image_height) > max_edge or (
        reply.image_width * reply.image_height > request.max_pixels
    ):
        raise ValueError("Desktop image exceeds the pixel budget")
    if reply.captured_at is None or not started - timedelta(seconds=1) <= (
        reply.captured_at
    ) <= datetime.now(UTC) + timedelta(seconds=1):
        raise ValueError("Desktop image timestamp is invalid")
    raw = base64.b64decode(reply.png_base64, validate=True)
    if len(raw) > request.max_bytes:
        raise ValueError("Desktop image exceeds the byte budget")
    validate_png_dimensions(raw, reply.image_width, reply.image_height)
    check()
    return DesktopOverview(
        image=PromptImage(
            capture_id=request.capture_id,
            captured_at=reply.captured_at,
            data_url="data:image/png;base64," + reply.png_base64,
            sha256=hashlib.sha256(raw).hexdigest(),
        ),
        layout=describe_layout(monitors, bounds),
    )
