"""Ephemeral audio-worker presentation relay. No HTTP input, replay, or durable records."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from sora.contracts.base import StrictModel
from sora.contracts.voice import VoiceEmotion

from .presentation import VoicePresentationResetReason


class LocalPresentationPacket(StrictModel):
    op: Literal["begin", "frame", "reset"]
    playback_id: str | None = Field(default=None, min_length=1, max_length=128)
    output_epoch: int | None = Field(default=None, ge=0)
    emotion: VoiceEmotion = VoiceEmotion.NEUTRAL
    sequence: int = Field(default=0, ge=0, le=1_000_000)
    position_ms: float = Field(default=0, ge=0, le=86_400_000, allow_inf_nan=False)
    duration_ms: float = Field(default=100, gt=0, le=1000, allow_inf_nan=False)
    mouth_open: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    # A, E, I, O, U mouth-shape shares from the audio; all zero means "use mouth_open alone".
    vowels: list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]] = Field(
        default_factory=lambda: [0.0] * 5, min_length=5, max_length=5
    )
    reason: VoicePresentationResetReason = VoicePresentationResetReason.DISCONNECTED
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def identity(self) -> LocalPresentationPacket:
        if self.emitted_at.tzinfo is None or self.emitted_at.utcoffset() is None:
            raise ValueError("Audio presentation timestamp must be timezone-aware")
        if self.op != "reset" and (self.playback_id is None or self.output_epoch is None):
            raise ValueError("Audio presentation requires a playback identity")
        return self


class LocalPresentationRelay:
    def __init__(self) -> None:
        self.stream_id = uuid.uuid4().hex
        self.serial = 0
        self.listeners: list[asyncio.Queue[dict[str, Any]]] = []

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=32)
        self.listeners.append(queue)
        # No begin/frame snapshot: reconnect never replays speech presentation.
        return queue

    def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self.listeners:
            self.listeners.remove(queue)

    def publish(self, data: dict[str, Any]) -> None:
        packet = LocalPresentationPacket.model_validate(data).model_dump(mode="json")
        self.serial += 1
        payload = {
            **packet,
            "stream_id": self.stream_id,
            "serial": self.serial,
        }
        for queue in self.listeners:
            if queue.full():
                # Never skip an ordered amplitude sample and then pretend continuity.
                while not queue.empty():
                    queue.get_nowait()
                    queue.task_done()
                queue.put_nowait(
                    {
                        **payload,
                        "op": "reset",
                        "playback_id": None,
                        "output_epoch": None,
                        "reason": "failed",
                    }
                )
            else:
                queue.put_nowait(payload)

    def reset(self) -> None:
        self.publish({"op": "reset", "reason": "disconnected"})
        self.stream_id = uuid.uuid4().hex
        self.serial = 0
