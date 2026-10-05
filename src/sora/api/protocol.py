"""Lightweight, standard-library HTTP/1.1 and RFC 6455 WebSocket protocol implementation."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import struct
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlparse

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

HTTP_STATUS_REASONS = {
    200: "OK",
    201: "Created",
    202: "Accepted",
    204: "No Content",
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    408: "Request Timeout",
    409: "Conflict",
    413: "Payload Too Large",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    503: "Service Unavailable",
}


class HttpProtocolError(ValueError):
    """A bounded HTTP request could not be parsed safely."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class WebSocketProtocolError(ConnectionError):
    """A peer sent an invalid RFC 6455 frame."""


class HttpRequest:
    """Represents an incoming HTTP request."""

    def __init__(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        self.method = method.upper()
        self.raw_path = path
        parsed = urlparse(path)
        self.path = parsed.path
        self.query_string = parsed.query
        self.headers = {k.lower(): v for k, v in headers.items()}
        self.body = body

    def query_params(self) -> dict[str, list[str]]:
        return parse_qs(self.query_string, keep_blank_values=True)

    def query_param(self, name: str, default: str | None = None) -> str | None:
        params = self.query_params()
        if name in params and params[name]:
            return params[name][0]
        return default

    def json(self) -> Any:
        if not self.body:
            return None
        return json.loads(self.body.decode("utf-8"))

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)


class HttpResponse:
    """Represents an HTTP response to be serialized and sent to client."""

    def __init__(
        self,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.body = body
        # Transport-only completion hook, never serialized into the response.
        self.after_send: Callable[[], None] | None = None

    @classmethod
    def json(
        cls,
        data: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        body = json.dumps(data, indent=2).encode("utf-8")
        hdrs = {
            "Content-Type": "application/json; charset=utf-8",
            "Content-Length": str(len(body)),
        }
        if headers:
            hdrs.update(headers)
        return cls(status_code=status_code, headers=hdrs, body=body)

    @classmethod
    def error(
        cls,
        status_code: int,
        message: str,
        code: str = "error",
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        payload = {"error": {"code": code, "message": message, "status": status_code}}
        return cls.json(payload, status_code=status_code, headers=headers)

    def serialize(self) -> bytes:
        reason = HTTP_STATUS_REASONS.get(self.status_code, "Unknown")
        lines = [f"HTTP/1.1 {self.status_code} {reason}\r\n"]

        if "Content-Length" not in self.headers:
            self.headers["Content-Length"] = str(len(self.body))
        if "Server" not in self.headers:
            self.headers["Server"] = "SORA-Core/1.0"
        # The Core HTTP handler serves one request per TCP connection.
        self.headers.setdefault("Connection", "close")

        for key, value in self.headers.items():
            lines.append(f"{key}: {value}\r\n")
        lines.append("\r\n")

        header_bytes = "".join(lines).encode("utf-8")
        return header_bytes + self.body

    def parse_json(self) -> Any:
        return json.loads(self.body.decode("utf-8"))


async def read_http_request(
    reader: asyncio.StreamReader,
    max_payload_bytes: int = 10 * 1024 * 1024,
    max_header_bytes: int = 64 * 1024,
) -> HttpRequest | None:
    """Reads and parses an HTTP request from an asyncio StreamReader."""
    try:
        line_bytes = await reader.readline()
        if not line_bytes:
            return None
        header_bytes_read = len(line_bytes)
        if header_bytes_read > max_header_bytes:
            raise HttpProtocolError(400, "HTTP request line exceeds the header limit")
        request_line = line_bytes.decode("utf-8", errors="replace").strip()
        parts = request_line.split(" ")
        if len(parts) < 2:
            raise HttpProtocolError(400, "Malformed HTTP request line")
        method, path = parts[0], parts[1]

        headers: dict[str, str] = {}
        while True:
            header_line_bytes = await reader.readline()
            header_bytes_read += len(header_line_bytes)
            if header_bytes_read > max_header_bytes:
                raise HttpProtocolError(400, "HTTP headers exceed the configured limit")
            if not header_line_bytes or header_line_bytes == b"\r\n" or header_line_bytes == b"\n":
                break
            header_line = header_line_bytes.decode("utf-8", errors="replace").strip()
            if ":" not in header_line:
                raise HttpProtocolError(400, "Malformed HTTP header")
            name, val = header_line.split(":", 1)
            headers[name.strip()] = val.strip()

        try:
            content_length = int(headers.get("content-length", headers.get("Content-Length", "0")))
        except ValueError as exc:
            raise HttpProtocolError(400, "Invalid Content-Length header") from exc
        if content_length < 0:
            raise HttpProtocolError(400, "Content-Length cannot be negative")
        if content_length > max_payload_bytes:
            raise HttpProtocolError(413, "HTTP payload exceeds the configured limit")

        body = b""
        if content_length > 0:
            body = await reader.readexactly(content_length)

        return HttpRequest(method=method, path=path, headers=headers, body=body)
    except HttpProtocolError:
        raise
    except (asyncio.IncompleteReadError, UnicodeError, ValueError) as exc:
        raise HttpProtocolError(400, "Incomplete or malformed HTTP request") from exc


class WebSocketSession:
    """Encapsulates a connected RFC 6455 WebSocket session."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        client_id: str,
        *,
        is_client: bool = False,
        max_message_bytes: int = 10 * 1024 * 1024,
    ) -> None:
        self.reader = reader
        self.writer = writer
        self.client_id = client_id
        self.is_client = is_client
        self.max_message_bytes = max_message_bytes
        self.closed = False
        self._write_lock = asyncio.Lock()

    async def send_text(self, text: str) -> None:
        """Send one final UTF-8 text frame with role-appropriate masking."""
        payload = text.encode("utf-8")
        if len(payload) > self.max_message_bytes:
            raise WebSocketProtocolError("WebSocket message exceeds configured limit")
        await self._send_frame(0x1, payload)

    async def send_json(self, data: Any) -> None:
        await self.send_text(json.dumps(data))

    async def send_close(self, code: int = 1000, reason: str = "") -> None:
        """Sends a close frame to the client."""
        reason_bytes = reason.encode("utf-8")
        payload = struct.pack("!H", code) + reason_bytes
        if len(payload) > 125:
            payload = struct.pack("!H", code) + reason_bytes[:123]
        await self._send_frame(0x8, payload)
        self.closed = True

    async def send_ping(self, payload: bytes = b"") -> None:
        await self._send_frame(0x9, payload)

    async def send_pong(self, payload: bytes = b"") -> None:
        await self._send_frame(0xA, payload)

    async def _send_frame(self, opcode: int, payload: bytes) -> None:
        if self.closed or self.writer.is_closing():
            return
        if opcode >= 0x8 and len(payload) > 125:
            raise WebSocketProtocolError("WebSocket control frame exceeds 125 bytes")
        mask_bit = 0x80 if self.is_client else 0
        frame = bytearray([0x80 | opcode])
        length = len(payload)
        if length < 126:
            frame.append(mask_bit | length)
        elif length <= 0xFFFF:
            frame.append(mask_bit | 126)
            frame.extend(struct.pack("!H", length))
        else:
            frame.append(mask_bit | 127)
            frame.extend(struct.pack("!Q", length))
        if self.is_client:
            mask_key = os.urandom(4)
            frame.extend(mask_key)
            frame.extend(bytes(byte ^ mask_key[index % 4] for index, byte in enumerate(payload)))
        else:
            frame.extend(payload)
        async with self._write_lock:
            try:
                self.writer.write(frame)
                await self.writer.drain()
            except (ConnectionResetError, BrokenPipeError):
                self.closed = True

    async def receive_text(self) -> str | None:
        """Receives next text frame, automatically handling pings/pongs/close."""
        fragments = bytearray()
        fragmented = False
        while not self.closed:
            try:
                header = await self.reader.readexactly(2)
            except (asyncio.IncompleteReadError, ConnectionResetError):
                self.closed = True
                return None

            b1, b2 = header[0], header[1]
            fin = bool(b1 & 0x80)
            if b1 & 0x70:
                await self.send_close(code=1002, reason="reserved_bits")
                raise WebSocketProtocolError("RSV bits require a negotiated extension")
            opcode = b1 & 0x0F
            masked = (b2 & 0x80) != 0
            if self.is_client and masked:
                await self.send_close(code=1002, reason="masked_server_frame")
                raise WebSocketProtocolError("Servers must not mask WebSocket frames")
            if not self.is_client and not masked:
                await self.send_close(code=1002, reason="unmasked_client_frame")
                raise WebSocketProtocolError("Clients must mask WebSocket frames")
            payload_len = b2 & 0x7F

            if payload_len == 126:
                ext = await self.reader.readexactly(2)
                payload_len = struct.unpack("!H", ext)[0]
            elif payload_len == 127:
                ext = await self.reader.readexactly(8)
                payload_len = struct.unpack("!Q", ext)[0]
                if payload_len >> 63:
                    await self.send_close(code=1002, reason="invalid_length")
                    raise WebSocketProtocolError("WebSocket 64-bit length has its high bit set")

            if opcode >= 0x8 and (not fin or payload_len > 125):
                await self.send_close(code=1002, reason="invalid_control_frame")
                raise WebSocketProtocolError("Invalid fragmented or oversized control frame")
            if payload_len > self.max_message_bytes:
                await self.send_close(code=1009, reason="message_too_large")
                raise WebSocketProtocolError("WebSocket message exceeds configured limit")

            mask_key = b""
            if masked:
                mask_key = await self.reader.readexactly(4)

            payload = await self.reader.readexactly(payload_len)
            if masked:
                payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

            # Opcode handlers
            if opcode == 0x8:  # Close
                code = struct.unpack("!H", payload[:2])[0] if len(payload) >= 2 else 1000
                await self.send_close(code=code)
                self.closed = True
                return None
            if opcode == 0x9:  # Ping
                await self.send_pong(payload)
                continue
            if opcode == 0xA:  # Pong
                continue
            if opcode == 0x1:  # Text frame
                if fragmented:
                    await self.send_close(code=1002, reason="unexpected_text_frame")
                    raise WebSocketProtocolError("New text frame arrived during fragmentation")
                if fin:
                    try:
                        return payload.decode("utf-8")
                    except UnicodeDecodeError as exc:
                        await self.send_close(code=1007, reason="invalid_utf8")
                        raise WebSocketProtocolError("Text frame is not valid UTF-8") from exc
                fragments.extend(payload)
                fragmented = True
                continue
            if opcode == 0x0:  # Continuation
                if not fragmented:
                    await self.send_close(code=1002, reason="unexpected_continuation")
                    raise WebSocketProtocolError("Unexpected continuation frame")
                fragments.extend(payload)
                if len(fragments) > self.max_message_bytes:
                    await self.send_close(code=1009, reason="message_too_large")
                    raise WebSocketProtocolError("Fragmented message exceeds configured limit")
                if fin:
                    try:
                        return bytes(fragments).decode("utf-8")
                    except UnicodeDecodeError as exc:
                        await self.send_close(code=1007, reason="invalid_utf8")
                        raise WebSocketProtocolError("Text message is not valid UTF-8") from exc
                continue
            if opcode == 0x2:
                await self.send_close(code=1003, reason="binary_not_supported")
                raise WebSocketProtocolError("Binary WebSocket messages are unsupported")
            await self.send_close(code=1002, reason="unsupported_opcode")
            raise WebSocketProtocolError(f"Unsupported WebSocket opcode: {opcode}")

        return None

    async def close(self) -> None:
        self.closed = True
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass


def is_websocket_upgrade_request(request: HttpRequest) -> bool:
    """Determines if the HTTP request is attempting a WebSocket upgrade."""
    conn = (request.header("Connection") or "").lower()
    upgrade = (request.header("Upgrade") or "").lower()
    return "upgrade" in conn and upgrade == "websocket"


def make_websocket_upgrade_response(request: HttpRequest) -> HttpResponse:
    """Generates the 101 Switching Protocols response for RFC 6455 handshake."""
    if request.header("Sec-WebSocket-Version") != "13":
        raise HttpProtocolError(400, "WebSocket version 13 is required")
    sec_key = request.header("Sec-WebSocket-Key") or ""
    try:
        decoded_key = base64.b64decode(sec_key, validate=True)
    except ValueError as exc:
        raise HttpProtocolError(400, "Invalid Sec-WebSocket-Key") from exc
    if len(decoded_key) != 16:
        raise HttpProtocolError(400, "Sec-WebSocket-Key must decode to 16 bytes")
    accept_val = base64.b64encode(hashlib.sha1((sec_key + WS_GUID).encode()).digest()).decode()

    headers = {
        "Upgrade": "websocket",
        "Connection": "Upgrade",
        "Sec-WebSocket-Accept": accept_val,
    }
    return HttpResponse(status_code=101, headers=headers, body=b"")
