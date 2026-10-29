"""Main API server lifecycle, connection dispatcher, and WebSocket upgrade handler."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import ssl
import stat
import uuid
from datetime import UTC, datetime

from sora.api.auth import (
    ApiAuthenticationError,
    ApiForbiddenError,
    ApiSecurityError,
    SecurityValidator,
    TokenAuthenticator,
)
from sora.api.config import ApiServerConfig
from sora.api.events import (
    EventBroadcaster,
    build_state_snapshot,
    get_stream_bounds,
    replay_events_since,
)
from sora.api.lifecycle import ManagedLifecycle
from sora.api.protocol import (
    HttpProtocolError,
    HttpRequest,
    HttpResponse,
    WebSocketProtocolError,
    WebSocketSession,
    is_websocket_upgrade_request,
    make_websocket_upgrade_response,
    read_http_request,
)
from sora.api.pwa import PwaAssetServer
from sora.api.remote import (
    DEFAULT_REMOTE_SCOPES,
    RemoteAccessError,
    RemoteAccessManager,
    SlidingWindowRateLimiter,
    required_remote_scope,
)
from sora.api.routes import RouteHandler
from sora.contracts.embodiment import EmbodimentFeedbackEvent, EmbodimentState
from sora.contracts.models import EventEnvelope
from sora.runtime.service import SoraRuntime
from sora.security.local_policy import owner_local_scope
from sora.security.operations import OperationAuthorizationError

logger = logging.getLogger(__name__)


class SoraApiServer:
    """Async HTTP/1.1 and WebSocket server exposing authenticated Core services."""

    def __init__(
        self, runtime: SoraRuntime, config: ApiServerConfig | None = None, *,
        lifecycle: ManagedLifecycle | None = None,
    ) -> None:
        self.runtime = runtime
        self.config = config or ApiServerConfig()
        self.authenticator = TokenAuthenticator(self.config.auth_token)
        self.security = SecurityValidator(self.config)
        self.routes = RouteHandler(runtime, lifecycle)
        self.pwa = PwaAssetServer()
        self.broadcaster = EventBroadcaster(self.config.client_buffer_capacity)
        self.remote_access = RemoteAccessManager(
            runtime.repository.database,
            runtime.config.owner_id,
            invitation_ttl_seconds=self.config.pairing_invitation_ttl_seconds,
            session_ttl_seconds=self.config.remote_session_ttl_seconds,
        )
        self.remote_rate_limiter = SlidingWindowRateLimiter()

        self._server: asyncio.Server | None = None
        self._remote_server: asyncio.Server | None = None
        self._outbox_task: asyncio.Task[None] | None = None
        self._websockets: dict[str, WebSocketSession] = {}
        self._serving = False
        self.actual_port: int = self.config.port
        self.actual_remote_port: int | None = None

    @property
    def is_serving(self) -> bool:
        return self._serving and self._server is not None and self._server.is_serving()

    async def start(self) -> None:
        """Starts the API server and event streaming pump."""
        if self._serving:
            return

        # Write token file if configured
        if self.config.token_file:
            self.config.token_file.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.config.token_file.with_suffix(f".tmp-{os.getpid()}")
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                stat.S_IRUSR | stat.S_IWUSR,
            )
            try:
                os.write(descriptor, self.config.auth_token.encode("utf-8"))
            finally:
                os.close(descriptor)
            os.replace(temporary, self.config.token_file)
            os.chmod(self.config.token_file, stat.S_IRUSR | stat.S_IWUSR)

        remote_tls: ssl.SSLContext | None = None
        if self.config.remote_access_enabled:
            certificate = self.config.remote_tls_certificate_file
            private_key = self.config.remote_tls_private_key_file
            assert certificate is not None and private_key is not None
            remote_tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            remote_tls.minimum_version = ssl.TLSVersion.TLSv1_2
            remote_tls.load_cert_chain(certificate, private_key)

        self._server = await asyncio.start_server(
            self._handle_client,
            host=self.config.host,
            port=self.config.port,
        )

        sockets = self._server.sockets
        if sockets:
            self.actual_port = sockets[0].getsockname()[1]

        if remote_tls is not None:
            try:
                self._remote_server = await asyncio.start_server(
                    self._handle_remote_client,
                    host=self.config.remote_host,
                    port=self.config.remote_port,
                    ssl=remote_tls,
                )
            except Exception:
                self._server.close()
                await self._server.wait_closed()
                self._server = None
                raise
            remote_sockets = self._remote_server.sockets
            if remote_sockets:
                self.actual_remote_port = remote_sockets[0].getsockname()[1]

        self._serving = True
        voice_host = "[::1]" if ":" in self.config.host else "127.0.0.1"
        self.runtime.local_voice.configure(
            f"http://{voice_host}:{self.actual_port}",
            self.config.auth_token,
        )
        self._outbox_task = asyncio.create_task(self._pump_outbox(), name="sora-api-outbox-pump")
        logger.info("SoraApiServer listening on %s:%d", self.config.host, self.actual_port)

    async def close(self) -> None:
        """Gracefully closes server, event pump, and active WebSocket connections."""
        if not self._serving:
            return
        self._serving = False
        await self.runtime.local_voice.close()

        if self._outbox_task:
            self._outbox_task.cancel()
            try:
                await self._outbox_task
            except asyncio.CancelledError:
                pass
            self._outbox_task = None

        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        if self._remote_server:
            self._remote_server.close()
            await self._remote_server.wait_closed()
            self._remote_server = None

        sessions = list(self._websockets.items())
        self._websockets.clear()
        for client_id, session in sessions:
            await self.broadcaster.unregister(client_id)
            try:
                await session.send_close(code=1001, reason="server_shutdown")
            except Exception:
                pass
            await session.close()

    async def _pump_outbox(self) -> None:
        """P08.2: Polls undelivered events from SQLite outbox and broadcasts them."""
        while self._serving:
            try:
                records = await self.runtime.runtime_repository.pending_outbox(limit=50)
                now = datetime.now(UTC)
                for rec in records:
                    envelope = EventEnvelope.model_validate_json(rec.payload)
                    await self.broadcaster.broadcast_event(envelope)
                    await self.runtime.runtime_repository.mark_outbox_delivered(rec.event_id, now)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Outbox pump iteration error: %s", exc)
            await asyncio.sleep(0.05)

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        remote: bool = False,
    ) -> None:
        """Handles an incoming TCP connection (HTTP or WebSocket)."""
        try:
            request = await asyncio.wait_for(
                read_http_request(
                    reader,
                    self.config.max_payload_bytes,
                    self.config.max_header_bytes,
                ),
                timeout=self.config.request_timeout_seconds,
            )
        except TimeoutError:
            await self._send_http_response(
                writer, HttpResponse.error(408, "HTTP request timed out", code="REQUEST_TIMEOUT")
            )
            return
        except HttpProtocolError as exc:
            await self._send_http_response(
                writer,
                HttpResponse.error(exc.status_code, exc.message, code="PROTOCOL_ERROR"),
            )
            return
        if not request:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        # P08.3 Security validations
        try:
            self.security.validate_request_path(request.raw_path)
            self.security.validate_host(request.header("Host"), remote=remote)
            self.security.validate_origin(request.header("Origin"), remote=remote)
        except ApiSecurityError as exc:
            await self._send_http_response(
                writer, HttpResponse.error(400, exc.message, code="SECURITY_VIOLATION")
            )
            return
        except ApiForbiddenError as exc:
            await self._send_http_response(
                writer, HttpResponse.error(403, exc.message, code="FORBIDDEN_ORIGIN")
            )
            return

        # CORS preflight options
        if request.method == "OPTIONS":
            cors_hdrs = self._cors_headers(request.header("Origin"), remote=remote)
            cors_hdrs.update(
                {
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": (
                        "Authorization, Content-Type, X-SORA-Device-ID, X-SORA-Grant-ID"
                    ),
                }
            )
            await self._send_http_response(writer, HttpResponse(204, headers=cors_hdrs))
            return

        source_ip = self._source_ip(writer)
        if remote and not self.remote_rate_limiter.allow(
            f"request:{source_ip}",
            limit=self.config.remote_request_limit,
            window_seconds=self.config.remote_request_window_seconds,
        ):
            await self.remote_access.audit(
                action="request.rate_limit",
                outcome="denied",
                source_ip=source_ip,
                method=request.method,
                path=request.path,
                details={"code": "RATE_LIMITED"},
            )
            await self._send_http_response(
                writer,
                self._prepare_remote_response(
                    HttpResponse.error(429, "Remote request rate exceeded", code="RATE_LIMITED"),
                    request.header("Origin"),
                ),
            )
            return

        # WebSocket Upgrade Handling (P08.2)
        if is_websocket_upgrade_request(request):
            if remote:
                await self._send_http_response(
                    writer,
                    self._prepare_remote_response(
                        HttpResponse.error(
                            403,
                            "Remote WebSocket transport is unavailable; use authenticated replay",
                            code="REMOTE_WEBSOCKET_UNAVAILABLE",
                        ),
                        request.header("Origin"),
                    ),
                )
                return
            await self._handle_websocket_upgrade(reader, writer, request)
            return

        # App-shell assets contain no token or user data. They are public on both
        # listeners, while every state-bearing route remains separately authenticated.
        if self.pwa.can_serve(request):
            await self._send_http_response(writer, self.pwa.serve(request))
            return

        if remote:
            handled = await self._handle_remote_pairing(request, source_ip=source_ip)
            if handled is not None:
                await self._send_http_response(
                    writer,
                    self._prepare_remote_response(handled, request.header("Origin")),
                )
                return

            if request.path != "/healthz":
                try:
                    principal = await self.remote_access.authenticate_session(
                        authorization=request.header("Authorization"),
                        device_id=request.header("X-SORA-Device-ID") or "",
                    )
                    required_scope = required_remote_scope(request.method, request.path)
                    if required_scope is None or required_scope not in principal.scopes:
                        raise RemoteAccessError(
                            403,
                            "REMOTE_SCOPE_DENIED",
                            "Remote session is not authorized for this operation",
                        )
                except RemoteAccessError as exc:
                    await self.remote_access.audit(
                        action="request.authorize",
                        outcome="denied",
                        source_ip=source_ip,
                        method=request.method,
                        path=request.path,
                        details={"code": exc.code},
                    )
                    await self._send_http_response(
                        writer,
                        self._prepare_remote_response(
                            HttpResponse.error(
                                exc.status_code,
                                exc.message,
                                code=exc.code,
                                headers={"WWW-Authenticate": 'SoraSession realm="SORA Core"'},
                            ),
                            request.header("Origin"),
                        ),
                    )
                    return
            else:
                principal = None

            response = await self.routes.handle_request(
                request,
                remote_scopes=principal.scopes if principal is not None else frozenset(),
            )
            if request.method == "GET" and request.path == "/api/v1/events":
                response = self._sanitize_remote_events(response)
            response = self._prepare_remote_response(response, request.header("Origin"))
            if principal is not None:
                audit_read = self.remote_rate_limiter.allow(
                    f"audit:{principal.session_id}:{request.path}",
                    limit=1,
                    window_seconds=60,
                )
                if request.method != "GET" or response.status_code >= 400 or audit_read:
                    await self.remote_access.audit(
                        action="request.route",
                        outcome="allowed" if response.status_code < 400 else "failed",
                        source_ip=source_ip,
                        method=request.method,
                        path=request.path,
                        device_id=principal.device_id,
                        session_id=principal.session_id,
                        details={"status": response.status_code},
                    )
            await self._send_http_response(writer, response)
            return

        # Standard HTTP Request Handling (P08.1)
        # /healthz and /readyz are unauthenticated liveness probes
        if request.path not in {"/healthz", "/readyz"}:
            try:
                self.authenticator.authenticate(request.header("Authorization"))
            except ApiAuthenticationError as exc:
                await self._send_http_response(
                    writer,
                    HttpResponse.error(
                        401,
                        exc.message,
                        code="UNAUTHORIZED",
                        headers={"WWW-Authenticate": 'Bearer realm="SORA Core"'},
                    ),
                )
                return

        pairing_response = await self._handle_local_pairing(request, source_ip=source_ip)
        if pairing_response is not None:
            pairing_response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Vary": "Authorization, Origin",
                }
            )
            if self.config.cors_enabled:
                pairing_response.headers.update(self._cors_headers(request.header("Origin")))
            await self._send_http_response(writer, pairing_response)
            return

        # Only the owner bearer-authenticated listener can enter static local policy.
        # Remote sessions use the separate branch above, regardless of device headers.
        with owner_local_scope():
            response = await self.routes.handle_request(request)
        if request.path.startswith("/api/"):
            # Defense in depth for browsers, intermediaries, and service workers.
            response.headers.update(
                {
                    "Cache-Control": "no-store",
                    "Pragma": "no-cache",
                    "Vary": "Authorization, Origin",
                }
            )
        if self.config.cors_enabled:
            response.headers.update(self._cors_headers(request.header("Origin")))
        await self._send_http_response(writer, response)

    async def _handle_remote_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await self._handle_client(reader, writer, remote=True)

    @staticmethod
    def _source_ip(writer: asyncio.StreamWriter) -> str:
        peer = writer.get_extra_info("peername")
        if isinstance(peer, tuple) and peer:
            return str(peer[0])
        return "unknown"

    @staticmethod
    def _sanitize_remote_events(response: HttpResponse) -> HttpResponse:
        """Expose event invalidation metadata without snapshot/message/task content."""

        if response.status_code != 200:
            return response
        payload = response.parse_json()
        if not isinstance(payload, dict):
            return HttpResponse.error(
                500, "Remote event response is invalid", code="INTERNAL_ERROR"
            )
        raw_events = payload.get("events", [])
        events = []
        if isinstance(raw_events, list):
            for event in raw_events:
                if isinstance(event, dict):
                    events.append(
                        {
                            key: event[key]
                            for key in ("sequence", "timestamp", "event_type", "revision")
                            if key in event
                        }
                    )
        return HttpResponse.json(
            {
                "events": events,
                "minimum_sequence": payload.get("minimum_sequence", 0),
                "latest_sequence": payload.get("latest_sequence", 0),
                "next_sequence": payload.get("next_sequence", 0),
                "more_available": bool(payload.get("more_available", False)),
                "resync_required": bool(payload.get("resync_required", False)),
                "reason": payload.get("reason"),
                "snapshot": None,
            }
        )

    def _prepare_remote_response(self, response: HttpResponse, origin: str | None) -> HttpResponse:
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "Vary": "Authorization, Origin",
            }
        )
        if self.config.cors_enabled:
            response.headers.update(self._cors_headers(origin, remote=True))
        return response

    async def _handle_remote_pairing(
        self, request: HttpRequest, *, source_ip: str
    ) -> HttpResponse | None:
        if request.method == "POST" and request.path == "/api/v1/pairing/claim":
            if not self.remote_rate_limiter.allow(
                f"pairing:{source_ip}",
                limit=self.config.pairing_attempt_limit,
                window_seconds=self.config.pairing_attempt_window_seconds,
            ):
                await self.remote_access.audit(
                    action="pairing.claim",
                    outcome="denied",
                    source_ip=source_ip,
                    method=request.method,
                    path=request.path,
                    details={"code": "RATE_LIMITED"},
                )
                return HttpResponse.error(429, "Pairing attempt rate exceeded", code="RATE_LIMITED")
            try:
                data = request.json() or {}
            except (UnicodeError, ValueError):
                return HttpResponse.error(400, "Pairing request is invalid", code="INVALID_REQUEST")
            try:
                result = await self.remote_access.claim_invitation(
                    code=str(data.get("pairing_code", "")),
                    device_id=str(data.get("device_id", "")),
                    label=str(data.get("label", "")),
                    source_ip=source_ip,
                )
            except RemoteAccessError as exc:
                await self.remote_access.audit(
                    action="pairing.claim",
                    outcome="denied",
                    source_ip=source_ip,
                    method=request.method,
                    path=request.path,
                    details={"code": exc.code},
                )
                return HttpResponse.error(exc.status_code, exc.message, code=exc.code)
            return HttpResponse.json(result, status_code=201)

        if request.method == "POST" and request.path == "/api/v1/pairing/session":
            if not self.remote_rate_limiter.allow(
                f"session:{source_ip}",
                limit=self.config.pairing_attempt_limit,
                window_seconds=self.config.pairing_attempt_window_seconds,
            ):
                await self.remote_access.audit(
                    action="session.create",
                    outcome="denied",
                    source_ip=source_ip,
                    method=request.method,
                    path=request.path,
                    details={"code": "RATE_LIMITED"},
                )
                return HttpResponse.error(429, "Session attempt rate exceeded", code="RATE_LIMITED")
            try:
                data = request.json() or {}
            except (UnicodeError, ValueError):
                return HttpResponse.error(400, "Session request is invalid", code="INVALID_REQUEST")
            requested = data.get("scopes")
            try:
                result = await self.remote_access.create_session(
                    authorization=request.header("Authorization"),
                    device_id=str(data.get("device_id", "")),
                    requested_scopes=(
                        [str(scope) for scope in requested] if isinstance(requested, list) else None
                    ),
                    source_ip=source_ip,
                )
            except RemoteAccessError as exc:
                await self.remote_access.audit(
                    action="session.create",
                    outcome="denied",
                    source_ip=source_ip,
                    method=request.method,
                    path=request.path,
                    details={"code": exc.code},
                )
                return HttpResponse.error(exc.status_code, exc.message, code=exc.code)
            return HttpResponse.json(result, status_code=201)
        return None

    async def _handle_local_pairing(
        self, request: HttpRequest, *, source_ip: str
    ) -> HttpResponse | None:
        if not request.path.startswith("/api/v1/pairing/"):
            return None
        if not self.config.remote_access_enabled:
            return HttpResponse.error(404, "Remote access is disabled", code="REMOTE_DISABLED")
        try:
            if request.method == "POST" and request.path == "/api/v1/pairing/invitations":
                data = request.json() or {}
                scopes = data.get("scopes", list(DEFAULT_REMOTE_SCOPES))
                result = await self.remote_access.create_invitation(
                    label=str(data.get("label", "New SORA device")),
                    scopes=[str(scope) for scope in scopes] if isinstance(scopes, list) else (),
                    expires_in_seconds=(
                        int(data["expires_in_seconds"])
                        if data.get("expires_in_seconds") is not None
                        else None
                    ),
                    source_ip=source_ip,
                )
                return HttpResponse.json(result, status_code=201)
            if request.method == "GET" and request.path == "/api/v1/pairing/devices":
                return HttpResponse.json({"devices": await self.remote_access.list_devices()})
            if request.method == "GET" and request.path == "/api/v1/pairing/audit":
                limit = int(request.query_param("limit", "100") or "100")
                return HttpResponse.json(
                    {"audit": await self.remote_access.list_audit(limit=limit)}
                )
            prefix = "/api/v1/pairing/devices/"
            if request.method == "POST" and request.path.startswith(prefix):
                parts = request.path[len(prefix) :].split("/")
                if len(parts) == 2 and parts[1] == "revoke":
                    result = await self.remote_access.revoke_device(parts[0], source_ip=source_ip)
                    return HttpResponse.json(result)
        except (RemoteAccessError, TypeError, ValueError) as exc:
            if isinstance(exc, RemoteAccessError):
                return HttpResponse.error(exc.status_code, exc.message, code=exc.code)
            return HttpResponse.error(400, "Pairing request is invalid", code="INVALID_REQUEST")
        return HttpResponse.error(404, "Pairing endpoint not found", code="NOT_FOUND")

    def _cors_headers(self, origin: str | None, *, remote: bool = False) -> dict[str, str]:
        if not self.config.cors_enabled or not origin:
            return {}
        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Credentials": "true",
        }

    async def _send_http_response(
        self, writer: asyncio.StreamWriter, response: HttpResponse
    ) -> None:
        try:
            writer.write(response.serialize())
            await writer.drain()
            if response.after_send is not None:
                response.after_send()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def _handle_websocket_upgrade(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        request: HttpRequest,
    ) -> None:
        """P08.2 & P08.3: Authenticates WebSocket handshake, upgrades, and streams events."""
        # Authenticate via header
        try:
            self.authenticator.authenticate(request.header("Authorization"))
        except ApiAuthenticationError as exc:
            await self._send_http_response(
                writer, HttpResponse.error(401, exc.message, code="UNAUTHORIZED")
            )
            return

        try:
            upgrade_resp = make_websocket_upgrade_response(request)
        except HttpProtocolError as exc:
            await self._send_http_response(
                writer,
                HttpResponse.error(exc.status_code, exc.message, code="WEBSOCKET_HANDSHAKE_ERROR"),
            )
            return
        writer.write(upgrade_resp.serialize())
        await writer.drain()

        client_id = f"client-{uuid.uuid4()}"
        ws = WebSocketSession(
            reader,
            writer,
            client_id,
            max_message_bytes=self.config.max_payload_bytes,
        )
        self._websockets[client_id] = ws
        stream_id = self.runtime.config.owner_id

        # Initial handshake frame from client: expects optional since_sequence cursor
        try:
            init_raw = await asyncio.wait_for(
                ws.receive_text(),
                timeout=self.config.websocket_hello_timeout_seconds,
            )
            if not init_raw:
                raise WebSocketProtocolError("WebSocket hello frame is required")
            init_data = json.loads(init_raw)
            if not isinstance(init_data, dict):
                raise ValueError("hello frame must be a JSON object")
            cursor_seq = int(init_data.get("since_sequence", 0))
        except (TimeoutError, ValueError, json.JSONDecodeError, WebSocketProtocolError):
            await ws.send_close(code=1008, reason="invalid_hello")
            await ws.close()
            self._websockets.pop(client_id, None)
            return

        if init_data.get("client_kind") == "embodiment":
            with owner_local_scope():
                await self._serve_embodiment(ws, request, client_id)
            return

        # Register before reading the replay high-water mark so commits cannot fall
        # into the gap between replay and live subscription.
        sub = await self.broadcaster.register(
            client_id,
            ws,
            stream_id,
            last_sequence=max(cursor_seq, 0),
        )

        min_seq, max_seq = await get_stream_bounds(self.runtime, stream_id)
        if cursor_seq < 0 or (min_seq > 0 and cursor_seq < min_seq - 1):
            snapshot = await build_state_snapshot(self.runtime, stream_id)
            cursor_seq = int(snapshot["latest_sequence"])
            await ws.send_json(
                {
                    "type": "resync_required",
                    "reason": "cursor_expired",
                    "latest_sequence": cursor_seq,
                    "snapshot": snapshot,
                }
            )
        else:
            replay_cursor = cursor_seq
            while replay_cursor < max_seq:
                replayed = await replay_events_since(
                    self.runtime,
                    stream_id,
                    since_sequence=replay_cursor,
                    limit=self.config.replay_limit,
                    through_sequence=max_seq,
                )
                if not replayed:
                    snapshot = await build_state_snapshot(self.runtime, stream_id)
                    replay_cursor = int(snapshot["latest_sequence"])
                    await ws.send_json(
                        {
                            "type": "resync_required",
                            "reason": "replay_gap",
                            "latest_sequence": replay_cursor,
                            "snapshot": snapshot,
                        }
                    )
                    break
                for event in replayed:
                    await ws.send_json({"type": "event", "envelope": event.model_dump(mode="json")})
                replay_cursor = replayed[-1].sequence

        # Start transmitter task
        async def transmit() -> None:
            while not ws.closed:
                try:
                    msg = await sub.queue.get()
                    await ws.send_json(msg)
                    sub.queue.task_done()
                except (asyncio.CancelledError, ConnectionResetError):
                    break

        tx_task = asyncio.create_task(transmit(), name=f"ws-tx-{client_id}")

        # Receiver loop (keeps connection open and processes pings/pongs/close)
        try:
            while not ws.closed:
                text = await ws.receive_text()
                if text is None:
                    break
        finally:
            tx_task.cancel()
            await asyncio.gather(tx_task, return_exceptions=True)
            await self.broadcaster.unregister(client_id)
            self._websockets.pop(client_id, None)
            await ws.close()

    async def _serve_embodiment(
        self, ws: WebSocketSession, request: HttpRequest, client_id: str
    ) -> None:
        """Live, non-replayed presentation channel, separate from durable task events."""
        queue = None
        sender = None
        voice_queue = None
        motion_queue = None
        try:
            await self.runtime.authorize_operation(
                grant_id=request.header("X-SORA-Grant-ID") or "",
                device_id=request.header("X-SORA-Device-ID") or "",
                resource="embodiment.connect",
            )
            queue = self.runtime.register_embodiment_queue()
            voice_queue = self.runtime.local_voice.presentation.register()
            # The motion stream (sora.embodiment.motion_service), beside the voice stream.
            motion_queue = (self.runtime.motion.register()
                            if self.runtime.motion is not None else None)
            await ws.send_json(
                {
                    "type": "embodiment.snapshot",
                    "projection": self.runtime.get_embodiment_projection(),
                }
            )

            async def transmit() -> None:
                assert queue is not None
                revision = self.runtime.topology_manager.revision
                try:
                    while not ws.closed:
                        # Recheck revoked/expired connection authority while idle too.
                        await self.runtime.authorize_operation(
                            grant_id=request.header("X-SORA-Grant-ID") or "",
                            device_id=request.header("X-SORA-Device-ID") or "",
                            resource="embodiment.connect",
                        )
                        current = self.runtime.topology_manager.revision
                        while motion_queue is not None and not motion_queue.empty():
                            await ws.send_json(
                                {"type": "embodiment.motion", **motion_queue.get_nowait()})
                        assert voice_queue is not None
                        while not voice_queue.empty():
                            sample = voice_queue.get_nowait()
                            voice_queue.task_done()
                            if sample["op"] == "reset" or (
                                self.runtime.app_settings is not None
                                and self.runtime.app_settings.active.local_companion.voice
                            ):
                                await ws.send_json({"type": "embodiment.voice", "sample": sample})
                        if current != revision:
                            await ws.send_json(
                                {
                                    "type": "embodiment.snapshot",
                                    "projection": self.runtime.get_embodiment_projection(),
                                }
                            )
                            revision = current
                        try:
                            command = await asyncio.wait_for(queue.get(), timeout=0.02)
                        except TimeoutError:
                            continue
                        queue.task_done()
                        if not await self.runtime.validate_embodiment_delivery(command):
                            continue
                        if (
                            command.topology_revision != self.runtime.topology_manager.revision
                            or (datetime.now(UTC) - command.created_at).total_seconds() > 30
                        ):
                            continue
                        # Send new topology before any command referring to it.
                        if revision != command.topology_revision:
                            await ws.send_json(
                                {
                                    "type": "embodiment.snapshot",
                                    "projection": self.runtime.get_embodiment_projection(),
                                }
                            )
                            revision = command.topology_revision
                        await ws.send_json(
                            {
                                "type": "embodiment.command",
                                "command": command.model_dump(mode="json"),
                            }
                        )
                except (OperationAuthorizationError, ConnectionError):
                    await ws.close()

            sender = asyncio.create_task(transmit(), name=f"embodiment-{client_id}")
            while not ws.closed:
                message = await ws.receive_text()
                if message is None:
                    break
                data = json.loads(message)
                if not isinstance(data, dict):
                    raise ValueError("embodiment message must be an object")
                await self.runtime.authorize_operation(
                    grant_id=request.header("X-SORA-Grant-ID") or "",
                    device_id=request.header("X-SORA-Device-ID") or "",
                    resource="embodiment.connect",
                )
                if data.get("type") == "embodiment.state":
                    state = EmbodimentState.model_validate(data.get("state"))
                    self.runtime.update_embodiment_state(state)
                elif data.get("type") == "embodiment.feedback":
                    feedback = EmbodimentFeedbackEvent.model_validate(data.get("event"))
                    self.runtime.record_embodiment_feedback(feedback)
                elif data.get("type") == "embodiment.motion" and self.runtime.motion is not None:
                    # A malformed motion message is dropped; it never closes her connection.
                    with contextlib.suppress(ValueError):
                        await self.runtime.motion.from_player(data)
                else:
                    raise ValueError("unsupported embodiment message")
        except (OperationAuthorizationError, ValueError, WebSocketProtocolError):
            await ws.send_close(code=1008, reason="embodiment_rejected")
        finally:
            if sender is not None:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            if queue is not None:
                self.runtime.unregister_embodiment_queue(queue)
            if voice_queue is not None:
                self.runtime.local_voice.presentation.unregister(voice_queue)
            if motion_queue is not None and self.runtime.motion is not None:
                self.runtime.motion.unregister(motion_queue)
            self._websockets.pop(client_id, None)
            await ws.close()
