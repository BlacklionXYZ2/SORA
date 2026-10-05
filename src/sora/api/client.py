"""Asynchronous client SDK for SORA API with automatic reconnect and event replay."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import ssl
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

from sora.api.protocol import WS_GUID, WebSocketProtocolError, WebSocketSession, read_http_request
from sora.contracts.errors import EventOrderingViolation
from sora.contracts.events import EventOrder, classify_event_order
from sora.contracts.models import EventEnvelope


class SoraApiClient:
    """Asynchronous client interacting with SORA API server over HTTP and WebSocket."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        auth_token: str = "",
        origin: str | None = None,
        device_id: str = "device-local",
        authorization_scheme: str = "Bearer",
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTP or HTTPS origin")
        self.scheme = parsed.scheme
        self.host = parsed.hostname
        self.port = parsed.port or (443 if parsed.scheme == "https" else 80)

        self.auth_token = auth_token
        self.authorization_scheme = authorization_scheme
        self.origin = origin or self.base_url
        self.device_id = device_id
        self.ssl_context = ssl_context
        self.last_sequence: int = 0
        self.last_envelope: EventEnvelope | None = None
        self._running_ws = False
        self._current_ws: WebSocketSession | None = None

    async def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Performs an async HTTP request to the API server."""
        connection_ssl: ssl.SSLContext | bool | None = None
        if self.scheme == "https":
            connection_ssl = self.ssl_context or ssl.create_default_context()
        reader, writer = await asyncio.open_connection(
            self.host,
            self.port,
            ssl=connection_ssl,
            server_hostname=self.host if connection_ssl else None,
        )
        try:
            req_hdrs: dict[str, str] = {
                "Host": f"{self.host}:{self.port}",
                "Origin": self.origin,
                "Connection": "close",
                "X-SORA-Device-ID": self.device_id,
            }
            if self.auth_token:
                req_hdrs["Authorization"] = f"{self.authorization_scheme} {self.auth_token}"
            if headers:
                req_hdrs.update(headers)

            payload_bytes = b""
            if body is not None:
                payload_bytes = json.dumps(body).encode("utf-8")
                req_hdrs["Content-Type"] = "application/json"
                req_hdrs["Content-Length"] = str(len(payload_bytes))

            lines = [f"{method.upper()} {path} HTTP/1.1\r\n"]
            for k, v in req_hdrs.items():
                lines.append(f"{k}: {v}\r\n")
            lines.append("\r\n")

            writer.write("".join(lines).encode("utf-8") + payload_bytes)
            await writer.drain()

            resp = await read_http_request(reader)
            if not resp:
                raise ConnectionError("Empty or malformed response from server")

            status_code = int(resp.path) if resp.path.isdigit() else 200
            parsed_body = resp.json()
            if parsed_body is None:
                parsed_body = {}
            return status_code, parsed_body
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def _request_dict(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        status, data = await self._request(method, path, body=body, headers=headers)
        if isinstance(data, dict):
            return status, data
        return status, {}

    async def _request_list(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        status, data = await self._request(method, path, body=body, headers=headers)
        if isinstance(data, list):
            return status, [x for x in data if isinstance(x, dict)]
        return status, []

    # --- HTTP REST Methods ---

    async def get_health(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/healthz")
        return data

    async def get_readiness(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/readyz")
        return data

    async def get_status(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/status")
        return data

    async def submit_task(
        self,
        intent: str,
        *,
        idempotency_key: str | None = None,
        explicit_provider: str | None = None,
        explicit_model: str | None = None,
        explicit_effort: str | None = None,
        is_local_only: bool = False,
        reference_utterance: str | None = None,
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"intent": intent, "is_local_only": is_local_only}
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        if explicit_provider:
            body["explicit_provider"] = explicit_provider
        if explicit_model is not None:
            body["explicit_model"] = explicit_model
        if explicit_effort is not None:
            body["explicit_effort"] = explicit_effort
        if reference_utterance:
            body["reference_utterance"] = reference_utterance
        if reference_id:
            body["reference_id"] = reference_id
        _, data = await self._request_dict(
            "POST",
            "/api/v1/tasks",
            body=body,
            headers={"X-SORA-Device-ID": self.device_id},
        )
        return data

    async def list_tasks(
        self, limit: int = 50, offset: int = 0, status: str | None = None
    ) -> dict[str, Any]:
        path = f"/api/v1/tasks?limit={limit}&offset={offset}"
        if status:
            path += f"&status={status}"
        _, data = await self._request_dict("GET", path)
        return data

    async def get_task(self, task_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("GET", f"/api/v1/tasks/{task_id}")
        return data

    async def steer_task(self, task_id: str, instruction: str) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/tasks/{task_id}/steer", body={"instruction": instruction}
        )
        return data

    async def cancel_task(self, task_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("POST", f"/api/v1/tasks/{task_id}/cancel")
        return data

    async def post_message(self, content: str) -> dict[str, Any]:
        _, data = await self._request_dict("POST", "/api/v1/messages", body={"content": content})
        return data

    async def dialogue(self, content: str) -> dict[str, Any]:
        """Run one canonical companion turn through Core."""

        _, data = await self._request_dict(
            "POST", "/api/v1/dialogue", body={"content": content}
        )
        return data

    async def list_messages(self, limit: int = 50) -> list[dict[str, Any]]:
        _, data = await self._request_list("GET", f"/api/v1/messages?limit={limit}")
        return data

    async def poll_events(
        self, since_sequence: int = 0, *, limit: int = 100
    ) -> dict[str, Any]:
        """Read one bounded replay page for browser-compatible reconnect clients."""

        _, data = await self._request_dict(
            "GET", f"/api/v1/events?since_sequence={since_sequence}&limit={limit}"
        )
        return data

    async def create_pairing_invitation(
        self,
        label: str,
        *,
        scopes: list[str] | None = None,
        expires_in_seconds: int | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"label": label}
        if scopes is not None:
            body["scopes"] = scopes
        if expires_in_seconds is not None:
            body["expires_in_seconds"] = expires_in_seconds
        _, data = await self._request_dict(
            "POST", "/api/v1/pairing/invitations", body=body
        )
        return data

    async def claim_pairing(
        self, pairing_code: str, *, device_id: str, label: str
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/pairing/claim",
            body={"pairing_code": pairing_code, "device_id": device_id, "label": label},
            headers={"Authorization": ""},
        )
        return data

    async def create_remote_session(
        self,
        device_credential: str,
        *,
        device_id: str,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"device_id": device_id}
        if scopes is not None:
            body["scopes"] = scopes
        _, data = await self._request_dict(
            "POST",
            "/api/v1/pairing/session",
            body=body,
            headers={"Authorization": f"SoraDevice {device_credential}"},
        )
        return data

    async def list_paired_devices(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/pairing/devices")
        return data

    async def revoke_paired_device(self, device_id: str) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/pairing/devices/{device_id}/revoke", body={}
        )
        return data

    async def list_remote_audit(self, limit: int = 100) -> dict[str, Any]:
        _, data = await self._request_dict("GET", f"/api/v1/pairing/audit?limit={limit}")
        return data

    async def start_voice_session(
        self, request: dict[str, Any], *, grant_id: str
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/voice/sessions",
            body=request,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def get_voice_session(self, session_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("GET", f"/api/v1/voice/sessions/{session_id}")
        return data

    async def send_voice_transcript(
        self,
        session_id: str,
        event: dict[str, Any],
        *,
        attention_grant_id: str = "",
    ) -> dict[str, Any]:
        headers = {"X-SORA-Attention-Grant-ID": attention_grant_id} if attention_grant_id else None
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/voice/sessions/{session_id}/transcript",
            body=event,
            headers=headers,
        )
        return data

    async def send_voice_device_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/voice/sessions/{session_id}/device", body=event
        )
        return data

    async def send_voice_playback_event(
        self, session_id: str, event: dict[str, Any]
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/voice/sessions/{session_id}/playback", body=event
        )
        return data

    async def interrupt_voice_session(
        self, session_id: str, request: dict[str, Any]
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/voice/sessions/{session_id}/interrupt", body=request
        )
        return data

    async def close_voice_session(self, session_id: str) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST", f"/api/v1/voice/sessions/{session_id}/close", body={}
        )
        return data

    async def list_workspaces(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/workspaces")
        return data

    async def diff_workspace(self, workspace_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("GET", f"/api/v1/workspaces/{workspace_id}/diff")
        return data

    async def validate_workspace(
        self,
        workspace_id: str,
        commands: list[str],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/validate",
            body={"commands": commands},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def integrate_workspace(
        self,
        workspace_id: str,
        *,
        grant_id: str,
        commit_message: str = "Integrated workspace",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"commit_message": commit_message}
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/workspaces/{workspace_id}/integrate",
            body=body,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def rollback_integration(
        self,
        integration_id: str,
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        path = f"/api/v1/integrations/{integration_id}/rollback"
        _, data = await self._request_dict(
            "POST", path, body={}, headers={"X-SORA-Grant-ID": grant_id}
        )
        return data

    async def get_companion_projection(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/projections/companion")
        return data

    async def get_settings_projection(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/projections/settings")
        return data

    async def get_objects_projection(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/projections/objects")
        return data

    async def present_desktop_object_affordance(
        self,
        object_id: str,
        affordance_request: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop-objects/{object_id}/affordances",
            body=affordance_request,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def get_capabilities_projection(self) -> dict[str, Any]:
        _, data = await self._request_dict("GET", "/api/v1/projections/capabilities")
        return data

    async def acquire_desktop_target(
        self,
        target: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/desktop/targets",
            body=target,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def revalidate_desktop_target(
        self,
        target_id: str,
        *,
        authority: str,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/revalidate",
            body={"authority": authority},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def present_desktop_target(
        self,
        target_id: str,
        *,
        verb: str,
        grant_id: str,
        marker_duration_seconds: float = 5.0,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/present",
            body={"verb": verb, "marker_duration_seconds": marker_duration_seconds},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def press_desktop_target(
        self,
        target_id: str,
        *,
        attempt_id: str,
        expected_name_after: str,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/press",
            body={
                "attempt_id": attempt_id,
                "expected_name_after": expected_name_after,
            },
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def prepare_desktop_press_interaction(
        self,
        target_id: str,
        *,
        attempt_id: str,
        expected_name_after: str,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/interactions/press",
            body={
                "attempt_id": attempt_id,
                "expected_name_after": expected_name_after,
            },
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def contact_desktop_interaction(self, attempt_id: str) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/interactions/{attempt_id}/contact",
            body={},
        )
        return data

    async def type_desktop_target(
        self,
        target_id: str,
        *,
        attempt_id: str,
        text: str,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/type",
            body={"attempt_id": attempt_id, "text": text, "mode": "replace"},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def prepare_desktop_type_interaction(
        self,
        target_id: str,
        *,
        attempt_id: str,
        text: str,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/desktop/targets/{target_id}/interactions/type",
            body={"attempt_id": attempt_id, "text": text, "mode": "replace"},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def ingest_cursor_samples(
        self,
        samples: list[dict[str, Any]],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/attention/cursor",
            body={"samples": samples},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def ingest_desktop_events(
        self,
        events: list[dict[str, Any]],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/desktop/events",
            body={"events": events},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def capture_desktop(
        self,
        request: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/desktop/capture",
            body=request,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def normalize_vision_evidence(
        self,
        request: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/vision/evidence",
            body=request,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def set_desktop_event_subscription(
        self,
        enabled: bool,
        *,
        grant_id: str = "",
    ) -> dict[str, Any]:
        headers = {"X-SORA-Grant-ID": grant_id} if grant_id else None
        _, data = await self._request_dict(
            "POST",
            "/api/v1/desktop/events/subscription",
            body={"enabled": enabled},
            headers=headers,
        )
        return data

    async def ingest_selection_sample(
        self,
        sample: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/attention/selection",
            body=sample,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def resolve_attention(
        self,
        source: str,
        reference_time: str,
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/attention/resolve",
            body={"source": source, "reference_time": reference_time},
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def capture_attention_crop(
        self,
        request: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/attention/crop",
            body=request,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def resolve_reference(
        self,
        utterance: str,
        *,
        explicit_reference_id: str | None = None,
        revalidation_grant_id: str = "",
        clarification_grant_id: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"utterance": utterance}
        if explicit_reference_id is not None:
            body["explicit_reference_id"] = explicit_reference_id
        headers: dict[str, str] = {}
        if revalidation_grant_id:
            headers["X-SORA-Revalidation-Grant-ID"] = revalidation_grant_id
        if clarification_grant_id:
            headers["X-SORA-Clarification-Grant-ID"] = clarification_grant_id
        _, data = await self._request_dict(
            "POST",
            "/api/v1/references/resolve",
            body=body,
            headers=headers,
        )
        return data

    async def pin_reference(
        self,
        reference_id: str,
        *,
        ttl_seconds: float = 3_600,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            "/api/v1/references/pin",
            body={"reference_id": reference_id, "ttl_seconds": ttl_seconds},
        )
        return data

    async def navigate_content(
        self,
        utterance: str,
        *,
        verb: str,
        navigation_grant_id: str,
        explicit_reference_id: str | None = None,
        line: int | None = None,
        column: int | None = None,
        presentation_grant_id: str = "",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"utterance": utterance, "verb": verb}
        if explicit_reference_id is not None:
            body["explicit_reference_id"] = explicit_reference_id
        if line is not None:
            body["line"] = line
        if column is not None:
            body["column"] = column
        headers = {"X-SORA-Grant-ID": navigation_grant_id}
        if presentation_grant_id:
            headers["X-SORA-Presentation-Grant-ID"] = presentation_grant_id
        _, data = await self._request_dict(
            "POST",
            "/api/v1/content/navigate",
            body=body,
            headers=headers,
        )
        return data

    async def submit_editor_task(
        self,
        intent: str,
        editor_context: dict[str, Any],
        *,
        grant_id: str,
        idempotency_key: str | None = None,
        explicit_provider: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"intent": intent, "editor_context": editor_context}
        if idempotency_key:
            body["idempotency_key"] = idempotency_key
        if explicit_provider:
            body["explicit_provider"] = explicit_provider
        _, data = await self._request_dict(
            "POST",
            "/api/v1/editor/tasks",
            body=body,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def present_editor_finding(
        self,
        task_id: str,
        finding: dict[str, Any],
        *,
        grant_id: str,
    ) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/tasks/{task_id}/editor-finding",
            body=finding,
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def list_extensions(self) -> list[dict[str, Any]]:
        _, data = await self._request_list("GET", "/api/v1/extensions")
        return data

    async def get_extension_schema(self, ext_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("GET", f"/api/v1/extensions/{ext_id}/schema")
        return data

    async def enable_extension(self, ext_id: str, *, grant_id: str) -> dict[str, Any]:
        _, data = await self._request_dict(
            "POST",
            f"/api/v1/extensions/{ext_id}/enable",
            headers={"X-SORA-Grant-ID": grant_id},
        )
        return data

    async def disable_extension(self, ext_id: str) -> dict[str, Any]:
        _, data = await self._request_dict("POST", f"/api/v1/extensions/{ext_id}/disable")
        return data

    # --- Reconnectable WebSocket Event Stream (P08.2) ---

    async def stream_events(
        self,
        on_event: Callable[[EventEnvelope], Awaitable[None]],
        on_resync: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        max_reconnects: int = 5,
    ) -> None:
        """Connects to WebSocket event stream with automatic replay and reconnection."""
        self._running_ws = True
        attempts = 0

        while self._running_ws and attempts < max_reconnects:
            try:
                reader, writer = await asyncio.open_connection(self.host, self.port)
                # WebSocket upgrade handshake
                sec_key = base64.b64encode(secrets.token_bytes(16)).decode()
                headers = [
                    "GET /api/v1/events/ws HTTP/1.1\r\n",
                    f"Host: {self.host}:{self.port}\r\n",
                    f"Origin: {self.origin}\r\n",
                    f"X-SORA-Device-ID: {self.device_id}\r\n",
                    "Upgrade: websocket\r\n",
                    "Connection: Upgrade\r\n",
                    f"Sec-WebSocket-Key: {sec_key}\r\n",
                    "Sec-WebSocket-Version: 13\r\n",
                ]
                if self.auth_token:
                    headers.append(f"Authorization: Bearer {self.auth_token}\r\n")
                headers.append("\r\n")

                writer.write("".join(headers).encode("utf-8"))
                await writer.drain()

                # Read 101 response
                resp = await read_http_request(reader)
                if not resp or resp.headers.get("upgrade", "").lower() != "websocket":
                    raise ConnectionError("WebSocket handshake failed")
                expected_accept = base64.b64encode(
                    hashlib.sha1((sec_key + WS_GUID).encode()).digest()
                ).decode()
                if resp.headers.get("sec-websocket-accept") != expected_accept:
                    raise ConnectionError("WebSocket handshake accept key did not validate")

                ws = WebSocketSession(reader, writer, "client-ws", is_client=True)
                self._current_ws = ws

                # Send hello with current sequence cursor (P08.2 replay cursor)
                await ws.send_json({"since_sequence": self.last_sequence})
                attempts = 0  # reset on successful connect

                try:
                    while self._running_ws:
                        try:
                            raw = await asyncio.wait_for(ws.receive_text(), timeout=0.2)
                        except TimeoutError:
                            continue

                        if raw is None:
                            break  # connection closed or dropped

                        msg = json.loads(raw)
                        msg_type = msg.get("type")

                        if msg_type == "resync_required":
                            self.last_sequence = int(msg.get("latest_sequence", 0))
                            self.last_envelope = None
                            if on_resync:
                                await on_resync(msg.get("snapshot", {}))

                        elif msg_type == "event":
                            envelope = EventEnvelope.model_validate(msg.get("envelope"))
                            if envelope.sequence <= self.last_sequence:
                                continue
                            if (
                                self.last_sequence > 0
                                and envelope.sequence != self.last_sequence + 1
                            ):
                                raise ConnectionError(
                                    f"event sequence gap after {self.last_sequence}: "
                                    f"received {envelope.sequence}"
                                )
                            try:
                                order = classify_event_order(self.last_envelope, envelope)
                            except EventOrderingViolation as exc:
                                raise ConnectionError(str(exc)) from exc
                            if order == EventOrder.DUPLICATE:
                                continue

                            self.last_envelope = envelope
                            self.last_sequence = envelope.sequence
                            await on_event(envelope)
                finally:
                    self._current_ws = None
                    try:
                        await ws.close()
                    except Exception:
                        pass

            except asyncio.CancelledError:
                self._running_ws = False
                break
            except (ConnectionError, OSError, WebSocketProtocolError):
                if not self._running_ws:
                    break
                attempts += 1
                await asyncio.sleep(min(0.05 * (2**attempts), 1.0))

    def stop_streaming(self) -> None:
        self._running_ws = False
        if self._current_ws is not None:
            try:
                self._current_ws.writer.close()
            except Exception:
                pass
