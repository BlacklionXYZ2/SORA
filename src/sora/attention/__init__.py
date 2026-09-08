"""SORA spatial attention, cursor tracking, and deixis resolution."""

from .buffer import CursorRingBuffer, CursorSample
from .gestures import detect_hover, recognize_circle

__all__ = [
    "CursorRingBuffer",
    "CursorSample",
    "detect_hover",
    "recognize_circle",
]
