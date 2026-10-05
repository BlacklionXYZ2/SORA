"""SORA spatial attention, cursor tracking, and deixis resolution."""

from .buffer import CursorRingBuffer, CursorSample
from .events import DesktopEventAttentionPolicy
from .gestures import detect_click, detect_hover, recognize_circle
from .tracker import (
    AttentionResolution,
    AttentionResolutionStatus,
    AttentionResolveRequest,
    AttentionTracker,
    CursorSampleBatch,
    SelectionSample,
)

__all__ = [
    "CursorRingBuffer",
    "CursorSample",
    "CursorSampleBatch",
    "SelectionSample",
    "AttentionResolveRequest",
    "AttentionResolution",
    "AttentionResolutionStatus",
    "AttentionTracker",
    "DesktopEventAttentionPolicy",
    "detect_click",
    "detect_hover",
    "recognize_circle",
]
