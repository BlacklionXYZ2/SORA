"""P03A.7 direct dialogue provider and Core handoff acceptance."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.models import ActiveCapabilitySet
from sora.providers.dialogue import (
    DialogueProviderError,
    DialogueTimeoutError,
    OpenAICompatibleDialogueProvider,
)
from sora.providers.mock import DeterministicProvider, FaultMode
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


class RecordingDialogueProvider:
    provider_name = "recording-direct"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, ActiveCapabilitySet | None]] = []
        self.fail = fail

    async def respond(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> str:
        self.calls.append((prompt, context, active_capabilities))
        if self.fail:
            raise DialogueProviderError("fixture unavailable")
        return f"Direct reply to {prompt}"

    async def stream_response(
        self,
        prompt: str,
        context: str,
        *,
        active_capabilities: ActiveCapabilitySet | None = None,
    ) -> AsyncIterator[str]:
        yield await self.respond(prompt, context, active_capabilities=active_capabilities)


@pytest.mark.asyncio
async def test_direct_dialogue_uses_core_context_and_stays_available_during_work(
    tmp_path: Path,
) -> None:
    direct = RecordingDialogueProvider()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(fault=FaultMode.DELAY, delay_seconds=0.3),
        dialogue_provider=direct,
    )
    await runtime.start()
    try:
        receipt = await runtime.submit_task("Check the project in the background")
        assert await runtime.dialogue("Hello SORA") == "Direct reply to Hello SORA"
        assert "[IDENTITY:persona.md]" in direct.calls[0][1]
        assert "sora.tasks.show" not in direct.calls[0][1]

        assert await runtime.dialogue("What is Cody doing with the task?")
        context = direct.calls[1][1]
        active = direct.calls[1][2]
        assert "Recent conversation (data)" in context
        assert "user: Hello SORA" in context
        assert receipt.task.task_id in context
        assert "[TASK_STATUS:" in context
        assert active is not None
        assert [cap.capability_id for cap in active.selected_capabilities] == ["sora.tasks.show"]
        assert await runtime.active_specialists()  # Reasoning runs independently.
        messages = await runtime.repository.list_messages(runtime.config.conversation_id)
        assert [message.role for message in messages[-4:]] == [
            "user", "assistant", "user", "assistant"
        ]
        assert messages[-3].provenance == "direct dialogue: recording-direct"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_remote_dialogue_scopes_exclude_history_and_tasks(tmp_path: Path) -> None:
    direct = RecordingDialogueProvider()
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        dialogue_provider=direct,
    )
    await runtime.start()
    try:
        await runtime.dialogue("Private earlier message")
        await runtime.submit_task("Private task")
        route = RouteHandler(runtime)
        request = HttpRequest(
            "POST", "/api/v1/dialogue", {}, json.dumps({"content": "Hello"}).encode()
        )
        result = await route.handle_request(
            request, remote_scopes=frozenset({"conversation:write"})
        )
        assert result.status_code == 201
        context = direct.calls[-1][1]
        assert "Private earlier message" not in context
        assert "[TASK_STATUS:" not in context
        assert direct.calls[-1][2] is not None
        assert direct.calls[-1][2].selected_capabilities == ()
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_direct_reply_explicitly_disables_server_default_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = OpenAICompatibleDialogueProvider(
        base_url="http://127.0.0.1:1234/v1", model="local-companion",
    )
    post = AsyncMock(return_value={"content": "The selected text is bef."})
    monkeypatch.setattr(provider, "_post_message", post)
    await provider.respond("What is selected?", "Fresh native selection: bef")
    assert post.call_args.args[0]["chat_template_kwargs"] == {"enable_thinking": False}
    hosted = OpenAICompatibleDialogueProvider(
        base_url="https://example.invalid/v1", model="hosted",
    )
    assert "chat_template_kwargs" not in hosted._request_body([])


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/dialogue", "/api/v1/dialogue/desktop"])
async def test_timeout_route_is_distinct_and_does_not_echo_backend_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, path: str,
) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
    )
    method = "dialogue_with_desktop_view" if path.endswith("/desktop") else "dialogue"
    monkeypatch.setattr(
        runtime, method, AsyncMock(side_effect=DialogueTimeoutError("secret detail"))
    )
    result = await RouteHandler(runtime).handle_request(
        HttpRequest("POST", path, {}, json.dumps({"content": "What is selected?"}).encode())
    )
    assert result.status_code == 503
    payload = result.body.decode()
    assert "DIALOGUE_TIMEOUT" in payload and "Dialogue timeout in Settings" in payload
    assert "secret detail" not in payload and "unavailable" not in payload


@pytest.mark.asyncio
async def test_failed_direct_response_does_not_leave_half_turn(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=IDENTITY_ROOT),
        provider=DeterministicProvider(),
        dialogue_provider=RecordingDialogueProvider(fail=True),
    )
    await runtime.start()
    try:
        with pytest.raises(DialogueProviderError):
            await runtime.dialogue("Do not persist half a turn")
        assert await runtime.repository.list_messages(runtime.config.conversation_id) == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_openai_compatible_adapter_sends_model_and_context_to_local_server() -> None:
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
            payload = json.loads(
                (await reader.readexactly(int(headers["content-length"]))).decode()
            )
            received.append({"payload": payload, "authorization": headers.get("authorization")})
            body = json.dumps(
                {"choices": [{"message": {"content": "Hello from direct."}}]}
            ).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n"
                + body
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
            base_url=f"http://127.0.0.1:{port}/v1",
            model="local-direct-model",
            api_key="fixture-secret",
        )
        reply = await provider.respond("How are you?", "SORA identity and context")
        assert reply == "Hello from direct."
        assert received[0]["authorization"] == "Bearer fixture-secret"
        payload = received[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["model"] == "local-direct-model"
        assert payload["messages"] == [
            {"role": "system", "content": "SORA identity and context"},
            {"role": "user", "content": "How are you?"},
        ]
    finally:
        server.close()
        await server.wait_closed()


def test_direct_endpoint_rejects_non_loopback_plain_http() -> None:
    with pytest.raises(ValueError, match="HTTPS or loopback HTTP"):
        OpenAICompatibleDialogueProvider(base_url="http://example.com/v1", model="test")


@pytest.mark.asyncio
async def test_direct_selection_is_independent_and_settings_redact_key(tmp_path: Path) -> None:
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path,
            identity_root=IDENTITY_ROOT,
            dialogue_backend="openai-compatible",
            dialogue_base_url="http://127.0.0.1:1234/v1",
            dialogue_model="local-chat",
            dialogue_api_key=SecretStr("never-present-in-settings"),
        ),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    try:
        assert isinstance(runtime.dialogue_provider, OpenAICompatibleDialogueProvider)
        assert "deterministic" in runtime.providers
        route = RouteHandler(runtime)
        response = await route.handle_request(
            HttpRequest("GET", "/api/v1/projections/settings", {}, b"")
        )
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["dialogue_backend"] == "openai-compatible"
        assert data["dialogue_model"] == "local-chat"
        assert data["dialogue_api_key_configured"] is True
        assert b"never-present-in-settings" not in response.body
    finally:
        await runtime.close()
