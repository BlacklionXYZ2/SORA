"""Owner-local file and explicit desktop-image dialogue acceptance."""

from __future__ import annotations

import asyncio
import base64
import json
import struct
import zlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import httpx
import pytest

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.capture import DesktopCaptureStatus
from sora.contracts.embodiment import MonitorDescriptor, ScreenRect
from sora.contracts.screen import ScreenViewChoice, ScreenViewKeyword
from sora.desktop.capture import WindowsCaptureBridge, WindowsCaptureReply, WindowsCaptureRequest
from sora.providers.dialogue import (
    DeterministicDialogueProvider,
    DialogueProviderError,
    OpenAICompatibleDialogueProvider,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"

@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 415, 422])
async def test_image_rejection_explains_model_configuration_without_leaking_server_body(
    monkeypatch: pytest.MonkeyPatch, status: int,
) -> None:
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(
        status, json={"error": "private server details"}, request=request,
    ))
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=transport, **kwargs),
    )
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1234/v1", model="text")
    with pytest.raises(DialogueProviderError, match="vision-capable") as error:
        await provider.respond_with_images("Look", "", ("data:image/png;base64,AAAA",))
    assert "private server details" not in str(error.value)


def png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + kind + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(b"\x00" + b"\x12\x34\x56\xff" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


class RecordingImageDialogue:
    provider_name = "recording-local-image"

    def __init__(self) -> None:
        self.contexts: list[str] = []
        self.images: list[tuple[str, ...]] = []
        self.view: ScreenViewKeyword = "none"
        self.view_prompts: list[str] = []

    async def respond(self, prompt: str, context: str, **_: object) -> str:
        self.contexts.append(context)
        return f"Read request: {prompt}"

    async def respond_with_images(
        self, prompt: str, context: str, image_data_urls: tuple[str, ...], **_: object
    ) -> str:
        self.contexts.append(context)
        self.images.append(image_data_urls)
        return f"Saw image for: {prompt}"

    async def stream_response(self, prompt: str, context: str, **_: object) -> AsyncIterator[str]:
        yield await self.respond(prompt, context)

    async def choose_screen_view(self, prompt: str) -> ScreenViewChoice:
        self.view_prompts.append(prompt)
        return ScreenViewChoice(view=self.view)


class FixtureCaptureBridge(WindowsCaptureBridge):
    frame_provenance = "deterministic_fixture"

    def __init__(self) -> None:
        self.requests: list[WindowsCaptureRequest] = []

    async def list_monitors(
        self,
    ) -> tuple[tuple[MonitorDescriptor, ...], str, tuple[int, int] | None]:
        monitor = MonitorDescriptor(
            id="FIXTURE", primary=True, rect=ScreenRect(x=0, y=0, width=2, height=2)
        )
        return (monitor,), monitor.id, (1, 1)

    async def capture(self, request: WindowsCaptureRequest) -> WindowsCaptureReply:
        self.requests.append(request)
        assert request.region is not None
        return WindowsCaptureReply(
            status=DesktopCaptureStatus.OK,
            captured_at=datetime.now(UTC),
            region=request.region,
            png_base64=base64.b64encode(png(2, 2)).decode(),
        )


class FailingCaptureBridge(FixtureCaptureBridge):
    """Capture helper that answers a capture with a non-OK status."""

    async def capture(self, request: WindowsCaptureRequest) -> WindowsCaptureReply:
        self.requests.append(request)
        assert request.region is not None
        return WindowsCaptureReply(
            status=DesktopCaptureStatus.ACCESS_DENIED,
            captured_at=datetime.now(UTC),
            region=request.region,
        )


@pytest.mark.asyncio
async def test_screen_view_provider_constrains_and_validates_keyword_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    received: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [
            {"message": {"content": '{"view":"screen"}'}}
        ]})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    provider = OpenAICompatibleDialogueProvider(base_url="http://127.0.0.1:1234/v1", model="2b")
    choice = await provider.choose_screen_view("What can you see?")
    assert choice.view == "screen"
    body = received[0]
    assert body["response_format"]["schema"] == ScreenViewChoice.model_json_schema()
    assert body["max_tokens"] == 64 and body["temperature"] == 0
    assert body["messages"][1]["content"] == "What can you see?"


@pytest.mark.asyncio
async def test_chat_screen_question_captures_frame_and_attaches_it(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    model.view = "screen"
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    bridge = FixtureCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        response = await runtime.dialogue("What can you see?")
        assert response == "Saw image for: What can you see?"
        assert model.view_prompts == ["What can you see?"]
        assert len(bridge.requests) == 1
        assert model.images[0][0].startswith("data:image/png;base64,")
        assert "screenshot" in model.contexts[-1]
        assert runtime.desktop_captures.count == 0
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert len(messages) == 2
        assert all("base64" not in message.content for message in messages)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_settings_backed_capture_never_mints_or_consumes_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = RecordingImageDialogue()
    model.view = "screen"
    settings = AppSettingsController(tmp_path, AppSettings())
    settings.provider = model
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), app_settings=settings,
    )
    runtime.windows_capture_bridge = FixtureCaptureBridge()
    await runtime.start()
    forbidden = AsyncMock(side_effect=AssertionError("Grant storage is not local policy"))
    for name in ("save_grant", "save_approval", "consume_grant"):
        monkeypatch.setattr(runtime.repository, name, forbidden)
    try:
        assert await runtime.dialogue("What can you see?") == "Saw image for: What can you see?"
        forbidden.assert_not_awaited()
        assert runtime.desktop_captures.count == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_chat_without_screen_request_never_captures(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    bridge = FixtureCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        response = await runtime.dialogue("How are you today?")
        assert response == "Read request: How are you today?"
        assert model.view_prompts == ["How are you today?"]
        assert bridge.requests == [] and model.images == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_remote_screen_request_is_never_classified_or_captured(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    model.view = "screen"
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    bridge = FixtureCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        route = RouteHandler(runtime)
        result = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue", {}, b'{"content":"What can you see?"}',
        ), remote_scopes=frozenset({"conversation:write"}))
        assert result.status_code == 201
        assert model.view_prompts == [] and bridge.requests == [] and model.images == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_failed_chat_capture_is_reported_to_the_model_truthfully(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    model.view = "screen"
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    bridge = FailingCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        response = await runtime.dialogue("What can you see?")
        assert response == "Read request: What can you see?"
        assert model.images == []
        assert len(bridge.requests) == 1
        assert "capture failed" in model.contexts[-1]
        assert runtime.desktop_captures.count == 0
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_owner_can_read_unconfigured_local_file_without_persisting_bytes(
    tmp_path: Path,
) -> None:
    model = RecordingImageDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    target = tmp_path / "private" / "note.txt"
    target.parent.mkdir()
    target.write_text("LOCAL_FILE_SENTINEL_8421", encoding="utf-8")
    await runtime.start()
    try:
        route = RouteHandler(runtime)
        body = json.dumps({
            "content": "Summarize my attached file", "file_paths": [str(target)]
        }).encode()
        result = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue", {}, body,
        ))
        assert result.status_code == 201
        assert "LOCAL_FILE_SENTINEL_8421" in model.contexts[-1]
        assert runtime.config.allowed_content_roots() == ()
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert len(messages) == 2
        assert "LOCAL_FILE_SENTINEL_8421" not in " ".join(m.content for m in messages)
        denied = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue", {},
            json.dumps({"content": f"Read file {target}"}).encode(),
        ), remote_scopes=frozenset({"conversation:write"}))
        assert denied.status_code == 403
        assert len(model.contexts) == 1
        owner_command = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue", {},
            json.dumps({"content": f"Read file {target}"}).encode(),
        ))
        assert owner_command.status_code == 201
        assert "LOCAL_FILE_SENTINEL_8421" in model.contexts[-1]
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_local_model_receives_image_as_chat_completion_part() -> None:
    received: list[dict[str, object]] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await reader.readline()
            headers: dict[str, str] = {}
            while line := await reader.readline():
                if line == b"\r\n":
                    break
                key, value = line.decode().split(":", 1)
                headers[key.lower()] = value.strip()
            received.append(json.loads(
                (await reader.readexactly(int(headers["content-length"]))).decode()
            ))
            body = b'{"choices":[{"message":{"content":"A blue square."}}]}'
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    try:
        assert server.sockets is not None
        port = server.sockets[0].getsockname()[1]
        provider = OpenAICompatibleDialogueProvider(
            base_url=f"http://127.0.0.1:{port}/v1", model="local-vision"
        )
        data_url = "data:image/png;base64," + base64.b64encode(png(2, 2)).decode()
        answer = await provider.respond_with_images("What is here?", "SORA identity", (data_url,))
        assert answer == "A blue square."
        assert received == [{
            "model": "local-vision", "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [
                {"role": "system", "content": "SORA identity"},
                {"role": "user", "content": [
                    {"type": "text", "text": "What is here?"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
        }]
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_local_image_file_reaches_multimodal_seam(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    target = tmp_path / "picture.png"
    target.write_bytes(png(2, 2))
    await runtime.start()
    try:
        response = await runtime.dialogue("What is this image?", file_paths=(str(target),))
        assert response == "Saw image for: What is this image?"
        assert model.images[0][0].startswith("data:image/png;base64,")
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert all("base64" not in message.content for message in messages)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_fixture_dialogue_does_not_pretend_to_see_pixels(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=DeterministicDialogueProvider(),
    )
    bridge = FixtureCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        route = RouteHandler(runtime)
        result = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue/desktop", {}, b'{"content":"Look"}'
        ))
        assert result.status_code == 422
        assert bridge.requests == []
        assert b"vision-capable" in result.body
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_one_shot_desktop_view_reaches_model_and_erases_frame(tmp_path: Path) -> None:
    model = RecordingImageDialogue()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "core", identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(), dialogue_provider=model,
    )
    bridge = FixtureCaptureBridge()
    runtime.windows_capture_bridge = bridge
    await runtime.start()
    try:
        route = RouteHandler(runtime)
        denied = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue/desktop", {}, b'{"content":"Look"}'
        ), remote_scopes=frozenset({"conversation:write"}))
        assert denied.status_code == 403
        assert bridge.requests == []

        result = await route.handle_request(HttpRequest(
            "POST", "/api/v1/dialogue/desktop", {}, b'{"content":"What is visible?"}'
        ))
        assert result.status_code == 201
        assert json.loads(result.body)["response"] == "Saw image for: What is visible?"
        assert len(bridge.requests) == 1
        assert model.images[0][0].startswith("data:image/png;base64,")
        assert runtime.desktop_captures.count == 0
        grants = await runtime.repository.database.read(
            lambda connection: connection.execute("SELECT payload FROM grants").fetchall()
        )
        assert len(grants) == 1
        assert json.loads(grants[0][0])["used_count"] == 1
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert len(messages) == 2
        assert all("base64" not in message.content for message in messages)
    finally:
        await runtime.close()
