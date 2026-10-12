"""Constrained calls on SORA's own llama.cpp server apply the grammar from the first token."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from sora.providers.dialogue import DialogueProviderError, OpenAICompatibleDialogueProvider

BASE = "http://127.0.0.1:18771/v1"


def serve(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response],
) -> list[httpx.Request]:
    seen: list[httpx.Request] = []
    real = httpx.AsyncClient

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    def client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(recording)
        return real(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    return seen


def llama(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/apply-template":
        return httpx.Response(200, json={"prompt": "<|turn>user\nsit<turn|>\n<|turn>model\n"})
    if request.url.path == "/completion":
        return httpx.Response(200, json={"content": '{"op":"pose","name":"sit"}'})
    return httpx.Response(404)


@pytest.mark.asyncio
async def test_managed_server_uses_template_and_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen = serve(monkeypatch, llama)
    provider = OpenAICompatibleDialogueProvider(
        base_url=BASE, model="sora-local", api_key="key", llama_native=True,
    )
    call = await provider.choose_call("sit", "[]", frozenset({"pose"}))
    assert call.root.op == "pose"
    assert [request.url.path for request in seen] == ["/apply-template", "/completion"]
    template = json.loads(seen[0].content)
    assert template["chat_template_kwargs"] == {"enable_thinking": False}
    completion = json.loads(seen[1].content)
    assert completion["prompt"].endswith("<|turn>model\n")
    assert completion["json_schema"]["discriminator"]["mapping"].keys() == {"pose", "finish"}
    assert completion["n_predict"] == 1024 and completion["temperature"] == 0
    assert all(request.headers["Authorization"] == "Bearer key" for request in seen)


@pytest.mark.asyncio
async def test_external_servers_keep_chat_completions(monkeypatch: pytest.MonkeyPatch) -> None:
    def chat(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"op":"finish"}'}}]})

    seen = serve(monkeypatch, chat)
    provider = OpenAICompatibleDialogueProvider(base_url=BASE, model="lm-studio-model")
    call = await provider.choose_call("hi", "[]", frozenset({"pose"}))
    assert call.root.op == "finish"
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_free_text_replies_are_unchanged_on_the_managed_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def chat(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        return httpx.Response(200, json={"choices": [{"message": {"content": "Hi!"}}]})

    serve(monkeypatch, chat)
    provider = OpenAICompatibleDialogueProvider(
        base_url=BASE, model="sora-local", llama_native=True
    )
    assert await provider.respond("hi", "context") == "Hi!"


@pytest.mark.asyncio
async def test_server_errors_become_provider_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    serve(monkeypatch, lambda request: httpx.Response(500))
    provider = OpenAICompatibleDialogueProvider(
        base_url=BASE, model="sora-local", llama_native=True
    )
    with pytest.raises(DialogueProviderError):
        await provider.choose_call("sit", "[]", frozenset({"pose"}))
