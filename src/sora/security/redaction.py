"""Secret-safe structured audit helpers."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from typing import Any

from sora.contracts.models import CapabilityRequest
from sora.security.policy import CapabilityDecision

REDACTED = "[REDACTED]"
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)\bBearer\s+[^\s,;]+"),
    re.compile(r"(?i)\b(api[_-]?key|token|password)\s*[:=]\s*[^\s,;]+"),
)


def redact_text(value: str, secrets: Sequence[str] = ()) -> str:
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, REDACTED)
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def redact_value(value: Any, secrets: Sequence[str] = ()) -> Any:
    if isinstance(value, str):
        return redact_text(value, secrets)
    if isinstance(value, Mapping):
        return {str(key): redact_value(item, secrets) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact_value(item, secrets) for item in value]
    return value


def audit_capability_decision(
    logger: logging.Logger,
    decision: CapabilityDecision,
    request: CapabilityRequest,
    *,
    secrets: Sequence[str] = (),
) -> None:
    fields = {
        "event": "capability_decision",
        "request_id": request.request_id,
        "grant_id": decision.grant_id,
        "operation": request.operation.value,
        "resource": request.resource,
        "allowed": decision.allowed,
        "reason": decision.reason.value,
    }
    logger.info("%s", json.dumps(redact_value(fields, secrets), sort_keys=True))
