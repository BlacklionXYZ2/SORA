"""Capability-aware handling of optional provider methods."""

from __future__ import annotations

from enum import StrEnum

from .models import ProviderCapabilities, ProviderError, ProviderErrorCode


class ProviderMethod(StrEnum):
    EVENTS = "events"
    STEER = "steer"
    CANCEL = "cancel"
    RESUME = "resume"


def unsupported_method(
    capabilities: ProviderCapabilities,
    method: ProviderMethod,
) -> ProviderError | None:
    """Return a typed unsupported error instead of implying unavailable behavior."""

    supported = {
        ProviderMethod.EVENTS: capabilities.events,
        ProviderMethod.STEER: capabilities.steer,
        ProviderMethod.CANCEL: capabilities.cancel,
        ProviderMethod.RESUME: capabilities.resume,
    }[method]
    if supported:
        return None
    return ProviderError(
        code=ProviderErrorCode.UNSUPPORTED,
        message=f"provider {capabilities.provider} does not support {method.value}",
        retryable=False,
    )
