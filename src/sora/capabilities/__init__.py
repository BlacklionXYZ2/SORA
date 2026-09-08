"""SORA dynamic capability resolution and structural authority dispatch."""

from .dispatch import CapabilityDeniedError, dispatch_capability
from .resolver import CapabilityRegistry, CapabilityResolver

__all__ = [
    "CapabilityDeniedError",
    "CapabilityRegistry",
    "CapabilityResolver",
    "dispatch_capability",
]
