from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from tests.providers.test_claude_code import make_request

from sora.contracts.models import ProviderErrorCode, ProviderOutcome
from sora.providers.base import MalformedProviderResult, ProviderLaunchError
from sora.providers.custom_endpoint import CustomEndpointProvider
from sora.runtime.agent_preferences import AgentPreferences, CustomEndpoint


def answering(content: Any, seen: list[dict[str, Any]] | None = None) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://127.0.0.1:9123/v1/chat/completions"
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"total_tokens": 7},
        })
    return httpx.MockTransport(handler)


def provider(transport: httpx.AsyncBaseTransport, **extra: Any) -> CustomEndpointProvider:
    return CustomEndpointProvider(
        "custom-1", nickname="Pip", port=9123, transport=transport, timeout_seconds=5, **extra,
    )


@pytest.mark.asyncio
async def test_answer_is_normalised_and_credited_to_the_nickname() -> None:
    seen: list[dict[str, Any]] = []
    answer = 'Drafted.\n{"conclusion": "Drafted the intro", "facts": ["It is short"]}'
    agent = provider(answering(answer, seen), model="local-coder")
    caps = await agent.capabilities()
    assert caps.provider == "custom-1" and caps.display_name == "Pip" and not caps.filesystem
    run_id = await agent.start(make_request())
    result = await agent.result(run_id)
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "Drafted the intro" and result.facts == ("It is short",)
    assert result.patch is not None and result.patch.provenance == "Pip normalized result"
    assert result.usage == {"total_tokens": 7}
    assert seen[0]["model"] == "local-coder" and seen[0]["stream"] is False
    assert "[TASK_INTENT]\nExplain the cache module" in seen[0]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_request_model_overrides_default_and_blank_model_is_omitted() -> None:
    seen: list[dict[str, Any]] = []
    await (agent := provider(answering("ok", seen))).start(make_request(model="other"))
    await agent.result("run-claude-1")
    await agent.start(make_request(run_id="run-2"))
    await agent.result("run-2")
    assert seen[0]["model"] == "other" and "model" not in seen[1]


@pytest.mark.asyncio
async def test_failures_are_reported_honestly() -> None:
    down = provider(httpx.MockTransport(lambda request: (_ for _ in ()).throw(
        httpx.ConnectError("refused", request=request))))
    await down.start(make_request())
    with pytest.raises(ProviderLaunchError) as raised:
        await down.result("run-claude-1")
    assert raised.value.code is ProviderErrorCode.UNAVAILABLE and "port 9123" in str(raised.value)

    broken = provider(httpx.MockTransport(lambda request: httpx.Response(500)))
    await broken.start(make_request())
    with pytest.raises(ProviderLaunchError, match="HTTP 500"):
        await broken.result("run-claude-1")

    empty = provider(answering(""))
    await empty.start(make_request())
    with pytest.raises(MalformedProviderResult):
        await empty.result("run-claude-1")

    with pytest.raises(ProviderLaunchError):
        await provider(answering("x")).start(make_request(reasoning_effort="high"))


@pytest.mark.asyncio
async def test_cancel_stops_a_pending_request() -> None:
    release = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        await release.wait()
        return httpx.Response(200, json={"choices": [{"message": {"content": "late"}}]})

    agent = provider(httpx.MockTransport(slow))
    await agent.start(make_request())
    await asyncio.sleep(0.01)
    await agent.cancel("run-claude-1")
    assert await agent.status("run-claude-1") == "cancelled"
    with pytest.raises(ProviderLaunchError) as raised:
        await agent.result("run-claude-1")
    assert raised.value.code is ProviderErrorCode.CANCELLED


def test_enabled_custom_agents_are_registered_at_startup(tmp_path: Path) -> None:
    import sora.__main__ as cli

    arguments = cli.parser().parse_args([
        "--root", str(tmp_path), "--claude-command", "no-claude", "--hermes-command",
        "no-hermes", "--codex-command", "no-codex", "--antigravity-command", "no-agy",
    ])
    agents = AgentPreferences(
        custom_2=CustomEndpoint(enabled=True, nickname="Pip", port=9123,
                                default_model="local-coder"),
        custom_3=CustomEndpoint(enabled=False, nickname="Off", port=9124),
    )
    registry = cli.build_provider_registry(arguments, agents).registry
    agent = registry["custom-2"]
    assert isinstance(agent, CustomEndpointProvider)
    assert agent.base_url == "http://127.0.0.1:9123/v1" and agent.model == "local-coder"
    assert "custom-3" not in registry and "custom-1" not in registry


@pytest.mark.asyncio
async def test_runtime_delegates_to_a_custom_agent_by_nickname(tmp_path: Path) -> None:
    from sora.contracts.models import TaskStatus
    from sora.runtime.app_settings import AppSettings, AppSettingsController
    from sora.runtime.service import RuntimeConfig, SoraRuntime
    from sora.security.local_policy import owner_local_scope

    agents = AgentPreferences(custom_1=CustomEndpoint(
        enabled=True, nickname="Pip", port=9123, spoken_aliases="pippa",
    ))
    settings = AppSettings.model_validate({"agents": agents.model_dump(mode="json")})
    state = tmp_path / "state"
    runtime = SoraRuntime(
        RuntimeConfig(root=state, identity_root=Path(__file__).resolve().parents[2] / "identity",
                      worker_count=1),
        providers={"custom-1": provider(answering("Here is the summary."))},
        app_settings=AppSettingsController(state, settings),
    )
    await runtime.start()
    try:
        assert runtime.routing_engine.agent_names.requested("ask pippa to summarise") == (
            "custom-1",
        )
        with owner_local_scope():
            receipt = await runtime.submit_task("Summarise my notes", explicit_provider="custom-1")
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=10)
        assert report.status is TaskStatus.COMPLETED, report.message
        assert report.result is not None and report.result.conclusion == "Here is the summary."
        snapshot = await runtime.agent_catalogue.snapshot()
        assert snapshot["providers"][0]["display_name"] == "Pip"
    finally:
        await runtime.close()
