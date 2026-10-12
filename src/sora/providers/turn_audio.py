"""The owner's spoken audio for the reply being written, for brains that hear audio natively.

Gemma 4 E2B and E4B carry an audio encoder in their projector, so the voice clip can go straight
to the brain instead of only Whisper's transcript. Core sets the clip for the length of one
voice turn; only the reply request reads it. Small decision calls (memory, motion, companion
calls) never receive audio, so they stay as cheap as before.
"""

from __future__ import annotations

import base64
import struct
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_TURN_AUDIO: ContextVar[str | None] = ContextVar("sora_turn_audio", default=None)

# Said to the brain beside the clip: the transcript is a hint, the audio is what was said.
SPOKEN_AUDIO_NOTE = (
    "[The owner said this out loud; the recording is attached. The text above is an automatic "
    "transcript and may contain mistakes. Answer what you hear.]"
)
MAX_WAV_BYTES = 2_000_000  # about 60 s of mono 16 kHz 16-bit audio


def current_turn_audio() -> str | None:
    return _TURN_AUDIO.get()


@contextmanager
def turn_audio(wav_base64: str | None) -> Iterator[None]:
    token = _TURN_AUDIO.set(wav_base64)
    try:
        yield
    finally:
        _TURN_AUDIO.reset(token)


def valid_wav_base64(value: str) -> bool:
    """A bounded RIFF/WAVE clip; anything else is ignored rather than sent to the model."""
    try:
        raw = base64.b64decode(value, validate=True)
    except ValueError:
        return False
    return 44 <= len(raw) <= MAX_WAV_BYTES and raw[:4] == b"RIFF" and raw[8:12] == b"WAVE"


def projector_modalities(path: Path) -> frozenset[str]:
    """Read clip.has_vision_encoder / clip.has_audio_encoder from a GGUF projector header.

    Only the metadata block is read, with hard limits; a malformed file reports no modalities.
    """
    wanted = {"clip.has_vision_encoder": "vision", "clip.has_audio_encoder": "audio"}
    found: set[str] = set()
    sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    try:
        with path.open("rb") as stream:
            if stream.read(4) != b"GGUF":
                return frozenset()
            stream.read(4)  # version
            _tensors, count = struct.unpack("<QQ", stream.read(16))
            if count > 4096:
                return frozenset()

            def text() -> str:
                (length,) = struct.unpack("<Q", stream.read(8))
                if length > 65_536:
                    raise ValueError("oversized key")
                return stream.read(length).decode("utf-8", "replace")

            def skip(kind: int) -> object:
                if kind == 8:
                    return text()
                if kind == 9:
                    inner, length = struct.unpack("<IQ", stream.read(12))
                    if length > 10_000_000:
                        raise ValueError("oversized array")
                    if inner in sizes:
                        stream.seek(sizes[inner] * length, 1)
                    else:
                        for _ in range(length):
                            skip(inner)
                    return None
                raw = stream.read(sizes[kind])
                return raw[0] if kind == 7 else None

            for _ in range(count):
                key = text()
                (kind,) = struct.unpack("<I", stream.read(4))
                value = skip(kind)
                if key in wanted and value:
                    found.add(wanted[key])
    except (OSError, ValueError, KeyError, struct.error):
        return frozenset()
    return frozenset(found)
