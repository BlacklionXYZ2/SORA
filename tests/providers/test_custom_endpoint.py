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


# A stand-in ACP agent: prose answer, records the model it was switched to and its cwd.
FAKE_ACP = """
import json, os, sys
model = None
for line in sys.stdin:
    m = json.loads(line); method = m.get('method'); rid = m.get('id'); params = m.get('params', {})
    if method == 'initialize':
        out = {'protocolVersion': 1}
    elif method == 'session/new':
        out = {'sessionId': 'acp-session-1'}
    elif method == 'session/set_model':
        model = params['modelId']; out = {}
    elif method == 'session/prompt':
        text = params['prompt'][0]['text']
        open('touched.txt', 'w').write('acp was here')
        answer = ('Summarised. ' + json.dumps({'conclusion': 'Summary by ' + str(model),
                  'files_changed': ['touched.txt']}) if 'TASK:' in text else 'no task')
        update = {'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'text': answer}}}
        print(json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': update}),
              flush=True)
        out = {'stopReason': 'end_turn'}
    else:
        out = {}
    print(json.dumps({'jsonrpc': '2.0', 'id': rid, 'result': out}), flush=True)
"""


@pytest.mark.asyncio
async def test_acp_custom_agent_runs_a_task_and_switches_model(tmp_path: Path) -> None:
    from sora.providers.custom_endpoint import CustomACPProvider

    script = tmp_path / "fake_acp.py"
    script.write_text(FAKE_ACP, encoding="utf-8")
    import sys

    agent = CustomACPProvider("custom-2", nickname="Juniper", command=sys.executable,
                              args=(str(script),), cwd=str(tmp_path), timeout_seconds=10)
    caps = await agent.capabilities()
    assert caps.provider == "custom-2" and caps.display_name == "Juniper" and caps.resume
    run_id = await agent.start(make_request(model="june-large"))
    result = await agent.result(run_id)
    assert result.conclusion == "Summary by june-large"
    assert result.files_changed == ("touched.txt",)
    assert result.patch is None or result.patch.provenance == "Juniper normalized result"
    assert await agent.session_id(run_id) == "acp-session-1"
    assert (tmp_path / "touched.txt").exists()
    project = tmp_path / "project"
    project.mkdir()
    bound = agent.for_project_root(str(project))
    await bound.start(make_request(run_id="run-in-project"))
    await bound.result("run-in-project")
    assert (project / "touched.txt").exists() and bound.writer_stopped("run-in-project")


@pytest.mark.asyncio
async def test_acp_custom_agent_that_is_missing_reports_unavailable(tmp_path: Path) -> None:
    from sora.providers.custom_endpoint import CustomACPProvider

    agent = CustomACPProvider("custom-2", nickname="Juniper", command=str(tmp_path / "nope"))
    with pytest.raises(ProviderLaunchError) as raised:
        await agent.start(make_request())
    assert raised.value.code is ProviderErrorCode.UNAVAILABLE
    assert "Juniper (ACP) could not be started" in str(raised.value)


def test_acp_settings_validation_and_argument_splitting() -> None:
    from pydantic import ValidationError

    from sora.providers.custom_endpoint import split_command_arguments

    CustomEndpoint(enabled=True, nickname="Juniper", protocol="acp", command="juniper")
    with pytest.raises(ValidationError, match="needs a command"):
        CustomEndpoint(enabled=True, nickname="Juniper", protocol="acp")
    with pytest.raises(ValidationError, match="needs a port"):
        CustomEndpoint(enabled=True, nickname="Pip")
    assert split_command_arguments('acp --root "C:\\My Projects" -v') == (
        "acp", "--root", "C:\\My Projects", "-v",
    )


def test_startup_registers_acp_agents_and_skips_missing_commands(tmp_path: Path) -> None:
    import sys

    import sora.__main__ as cli
    from sora.providers.custom_endpoint import CustomACPProvider

    arguments = cli.parser().parse_args([
        "--root", str(tmp_path), "--claude-command", "no-claude", "--hermes-command",
        "no-hermes", "--codex-command", "no-codex", "--antigravity-command", "no-agy",
    ])
    agents = AgentPreferences(
        custom_1=CustomEndpoint(enabled=True, nickname="Juniper", protocol="acp",
                                command=sys.executable, arguments='agent.py --acp'),
        custom_2=CustomEndpoint(enabled=True, nickname="Ghost", protocol="acp",
                                command=str(tmp_path / "missing-agent")),
    )
    plan = cli.build_provider_registry(arguments, agents)
    agent = plan.registry["custom-1"]
    assert isinstance(agent, CustomACPProvider)
    assert agent.args == ("agent.py", "--acp") and agent.nickname == "Juniper"
    assert "custom-2" not in plan.registry
    assert any(item.startswith("custom-2:") for item in plan.skipped)
