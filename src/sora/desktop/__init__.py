"""Core-owned desktop observation, target, and authorized action services."""

from .actions import (
    WindowsActionBridge,
    WindowsActionReply,
    WindowsPressRequest,
    WindowsTypeBridge,
    WindowsTypeRequest,
)
from .bridge import WindowsObservationBridge
from .capture import WindowsCaptureBridge, WindowsCaptureReply, WindowsCaptureRequest
from .events import DesktopEventSource, WindowsDesktopEventSource
from .targets import DesktopTargetError, DesktopTargetRegistry

__all__ = [
    "DesktopTargetError",
    "DesktopTargetRegistry",
    "DesktopEventSource",
    "WindowsActionBridge",
    "WindowsActionReply",
    "WindowsCaptureBridge",
    "WindowsCaptureReply",
    "WindowsCaptureRequest",
    "WindowsObservationBridge",
    "WindowsPressRequest",
    "WindowsTypeBridge",
    "WindowsTypeRequest",
    "WindowsDesktopEventSource",
]
