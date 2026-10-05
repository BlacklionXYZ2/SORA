"""Separate, ephemeral authority for a positively owned desktop-host launch.

Owner API authentication and Core instance binding remain required in addition to
this credential. Nothing here grants the companion or remote clients lifecycle
authority. No process termination or adoption of an external runtime occurs.
"""

from __future__ import annotations

import asyncio
import hmac
import os
import re
from uuid import UUID

from pydantic import SecretStr

from sora.api.protocol import HttpRequest, HttpResponse
from sora.contracts.runtime_lifecycle import RuntimeLifecycle, RuntimeShutdownRequest

SESSION_ENV = "SORA_DESKTOP_HOST_SESSION"
CONTROL_ENV = "SORA_DESKTOP_HOST_CONTROL_TOKEN"


class ManagedLifecycle:
    def __init__(self, session_id: UUID, credential: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", credential):
            raise ValueError("Managed launch credential is invalid")
        self.session_id = session_id
        self._credential = SecretStr(credential)
        self.shutdown = asyncio.Event()
        self._request_id: UUID | None = None

    @classmethod
    def from_environment(cls) -> ManagedLifecycle | None:
        # Consume before creating model/provider/helper children. Do not inherit
        # shutdown authority into their environments or persist it in settings.
        session = os.environ.pop(SESSION_ENV, None)
        credential = os.environ.pop(CONTROL_ENV, None)
        if session is None and credential is None:
            return None
        if session is None or credential is None:
            raise ValueError("Managed launch environment is incomplete")
        try:
            session_id = UUID(session)
        except ValueError:
            raise ValueError("Managed launch session is invalid") from None
        return cls(session_id, credential)

    def projection(self, instance_id: str) -> RuntimeLifecycle:
        return RuntimeLifecycle(
            instance_id=UUID(instance_id), managed_session_id=self.session_id,
            state="shutdown_requested" if self._request_id else "managed",
            shutdown_request_id=self._request_id,
        )

    @property
    def shutdown_requested(self) -> bool:
        return self._request_id is not None

    def request_shutdown(self, request: HttpRequest, instance_id: str) -> HttpResponse:
        if request.header("X-SORA-Core-Instance") != instance_id:
            return HttpResponse.error(409, "Resync the owned Core instance first",
                                      code="RUNTIME_CHANGED")
        credential = request.header("X-SORA-Host-Control") or ""
        if not credential.isascii() or not hmac.compare_digest(
            credential, self._credential.get_secret_value(),
        ):
            return HttpResponse.error(403, "Managed launch ownership is required",
                                      code="HOST_OWNERSHIP_REQUIRED")
        if len(request.body) > 1024:
            return HttpResponse.error(413, "Lifecycle request is too large",
                                      code="PAYLOAD_TOO_LARGE")
        try:
            command = RuntimeShutdownRequest.model_validate_json(request.body)
        except ValueError:
            # Do not echo untrusted request values or credentials in diagnostics.
            return HttpResponse.error(400, "Invalid lifecycle request",
                                      code="INVALID_LIFECYCLE_REQUEST")
        if command.managed_session_id != self.session_id:
            return HttpResponse.error(409, "Managed launch session changed",
                                      code="HOST_SESSION_CHANGED")
        if self._request_id is not None and self._request_id != command.request_id:
            return HttpResponse.error(409, "Shutdown already requested; reuse its request ID",
                                      code="SHUTDOWN_ALREADY_REQUESTED")
        self._request_id = command.request_id
        response = HttpResponse.json(self.projection(instance_id).model_dump(mode="json"),
                                     status_code=202)
        # Routing/acceptance alone is not shutdown. The HTTP transport flushes the
        # acknowledgement before notifying the CLI's normal awaited cleanup path.
        # Failed delivery is retriable with exactly the same request ID.
        response.after_send = self.shutdown.set
        return response
