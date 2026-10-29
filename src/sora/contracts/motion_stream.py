"""The motion stream between Core, her player and a motion model (2026-10-27).

Live presentation data on the embodiment WebSocket, beside ``embodiment.voice``: never replayed,
never stored. Poses are motion-lab's **canonical** skeleton (22 joints, her proportions,
right-handed: +Y up, facing +Z, her left +X), local rotations as quaternions ``[x, y, z, w]``;
her player converts to and from Unity's frame (``Canonical.ToUnity``).

Core → player (``{"type": "embodiment.motion", ...}``, :class:`CoreMotionMessage`):
- ``source``: who moves her now, ``algorithmic`` (her own poses) or a model (``ardy``);
- ``record``: start recording her actual pose, for a handover seed;
- ``seed_request``: send the recording now;
- ``chunk``: the next 0.4 s of model motion (:class:`MotionChunk`).

Player → Core (:class:`PlayerMotionMessage`):
- ``seed``: her recorded pose (:class:`MotionSeed`);
- ``signal``: what she is doing (a phrase key, ``intent|emotion|intensity`` with ``-`` for
  unknown) and the velocity she should travel at, m/s in the canonical frame (zero when she
  shouldn't travel).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from sora.contracts.base import StrictModel

JOINTS = 22
Finite = Annotated[float, Field(allow_inf_nan=False, ge=-1000, le=1000)]
Unit = Annotated[float, Field(allow_inf_nan=False, ge=-1.0001, le=1.0001)]
Quaternion = Annotated[list[Unit], Field(min_length=4, max_length=4)]
PhraseKey = Annotated[str, Field(pattern=r"^[a-z_-]{1,16}\|[a-z-]{1,16}\|[a-z-]{1,8}$")]


class MotionFrame(StrictModel):
    root: Annotated[list[Finite], Field(min_length=3, max_length=3)]
    rot: Annotated[list[Quaternion], Field(min_length=JOINTS, max_length=JOINTS)]
    contacts: Annotated[list[bool], Field(min_length=4, max_length=4)] = Field(
        default_factory=lambda: [False] * 4)


class MotionChunk(StrictModel):
    seq: int = Field(ge=0)
    t0: float = Field(ge=0, allow_inf_nan=False)
    fps: Literal[60] = 60
    prompt: str = Field(default="", max_length=200)
    frames: list[MotionFrame] = Field(min_length=1, max_length=64)


class MotionSeed(StrictModel):
    fps: int = Field(ge=10, le=120)
    frames: list[MotionFrame] = Field(min_length=2, max_length=400)


class CoreMotionMessage(StrictModel):
    op: Literal["source", "record", "seed_request", "chunk"]
    source: Literal["algorithmic", "ardy"] | None = None
    seconds: float | None = Field(default=None, gt=0, le=10, allow_inf_nan=False)
    chunk: MotionChunk | None = None

    @model_validator(mode="after")
    def payload(self) -> CoreMotionMessage:
        if (self.op == "source") != (self.source is not None):
            raise ValueError("source messages, and only they, name a source")
        if (self.op == "chunk") != (self.chunk is not None):
            raise ValueError("chunk messages, and only they, carry a chunk")
        if self.op == "record" and self.seconds is None:
            raise ValueError("record needs seconds")
        return self


class PlayerMotionMessage(StrictModel):
    op: Literal["seed", "signal"]
    seed: MotionSeed | None = None
    key: PhraseKey | None = None
    velocity: Annotated[list[Finite], Field(min_length=2, max_length=2)] | None = None

    @model_validator(mode="after")
    def payload(self) -> PlayerMotionMessage:
        if (self.op == "seed") != (self.seed is not None):
            raise ValueError("seed messages, and only they, carry a seed")
        if self.op == "signal" and (self.key is None or self.velocity is None):
            raise ValueError("a signal needs a key and a velocity")
        return self
