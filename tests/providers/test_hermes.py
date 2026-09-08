from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, ProviderOutcome, ProviderRequest
from sora.providers.base import MalformedProviderResult, ProviderLaunchError
from sora.providers.hermes import HermesACPProvider, parse_hermes_result


def request(
    *,
    project_id: str | None = "project-sora",
    run_id: str = "run-1",
) -> ProviderRequest:
    from datetime import UTC, datetime, timedelta

    return ProviderRequest(
        request_id=f"request-{run_id}",
        task_id="task-1",
        run_id=run_id,
        owner_id="owner-local",
        project_id=project_id,
        intent="Do the task",
        context="AUTHORITATIVE_STATE\nFACT: existing",
        context_manifest_ref="context-1",
        deadline=datetime.now(UTC) + timedelta(seconds=10),
        artifact_destination="C:/tmp/artifacts",
        idempotency_key=f"provider-start-{run_id}",
    )


def test_hermes_json_result_is_normalized_into_a_patch() -> None:
    result = parse_hermes_result(
        '{"conclusion":"done","facts":["verified"],"actions_taken":["checked"],'
        '"memory_updates":["remember this"],"suggested_response":"Finished"}',
        request(),
    )
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "done"
    assert result.patch is not None
    assert len(result.patch.operations) == 2
    assert result.suggested_response == "Finished"
    fact = result.patch.operations[0]
    assert fact.operation == "propose_fact"
    assert fact.fact.epistemic_status == "inference"
    assert fact.fact.confidence == 0.5


def test_hermes_result_can_be_fenced_and_unknown_fields_are_ignored() -> None:
    result = parse_hermes_result(
        '```json\n{"conclusion":"done","facts":[],"extra":true}\n```',
        request(),
    )
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.patch is None


def test_owner_only_result_uses_the_repository_scope_contract() -> None:
    result = parse_hermes_result(
        '{"conclusion":"done","facts":["candidate"]}',
        request(project_id=None),
    )
    assert result.patch is not None
    assert result.patch.scope == "owner-local"


def test_invalid_known_list_field_fails_instead_of_silently_disappearing() -> None:
    with pytest.raises(MalformedProviderResult):
        parse_hermes_result('{"conclusion":"done","facts":"not-a-list"}', request())


@pytest.mark.asyncio
async def test_missing_hermes_executable_is_typed_unavailable(tmp_path: Path) -> None:
    provider = HermesACPProvider(command=str(tmp_path / "missing-hermes.exe"))
    with pytest.raises(ProviderLaunchError) as captured:
        await provider.start(request())
    assert captured.value.code is ProviderErrorCode.UNAVAILABLE


@pytest.mark.asyncio
async def test_fake_acp_process_supports_start_and_result(tmp_path: Path) -> None:
    script = tmp_path / "fake_acp.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialize':\n"
        "  assert __import__('os').environ.get('HERMES_ACP_SKIP_CONFIGURED_MCP') is None\n"
        "  out={'protocolVersion':1}\n"
        " elif method == 'session/new': out={'sessionId':'session-1'}\n"
        " elif method == 'session/load':\n"
        "  history={'update':{'sessionUpdate':'agent_message_chunk',"
        "'content':{'text':'{\\\"conclusion\\\":\\\"old history\\\"}'}}}\n"
        "  response={'jsonrpc':'2.0','method':'session/update','params':history}\n"
        "  print(json.dumps(response),flush=True); out={}\n"
        " elif method == 'session/prompt':\n"
        "  update = {'update': {'sessionUpdate': 'agent_message_chunk', "
        "'content': {'text': '{\\\"conclusion\\\":\\\"fake done\\\"}'}}}\n"
        "  print(json.dumps({'jsonrpc':'2.0','method':'session/update', "
        "'params': update}), flush=True)\n"
        "  out={}\n"
        " else: out={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':rid,'result':out}), flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(command=sys.executable, args=(str(script),), timeout_seconds=3)
    capabilities = await provider.capabilities()
    assert capabilities.provider == "hermes-acp"
    assert not capabilities.events
    assert capabilities.resume
    run_id = await provider.start(request())
    assert await provider.start(request()) == run_id
    result = await provider.result(run_id)
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "fake done"
    session_id = await provider.session_id(run_id)
    assert session_id == "session-1"
    assert await provider.status(run_id) == "unknown"

    resumed_run = await provider.resume(session_id, request(run_id="run-2"))
    resumed = await provider.result(resumed_run)
    assert resumed.outcome is ProviderOutcome.COMPLETED
    assert resumed.conclusion == "fake done"
    assert await provider.session_id(resumed_run) == session_id


@pytest.mark.asyncio
async def test_output_limit_stops_unbounded_acp_collection(tmp_path: Path) -> None:
    script = tmp_path / "large_acp.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialize': out={'protocolVersion':1}\n"
        " elif method == 'session/new': out={'sessionId':'session-1'}\n"
        " elif method == 'session/prompt':\n"
        "  update={'update':{'sessionUpdate':'agent_message_chunk','content':{'text':'x'*50}}}\n"
        "  response={'jsonrpc':'2.0','method':'session/update','params':update}\n"
        "  print(json.dumps(response),flush=True)\n"
        "  out={}\n"
        " else: out={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(
        command=sys.executable,
        args=(str(script),),
        timeout_seconds=3,
        max_output_chars=20,
    )
    run_id = await provider.start(request())
    with pytest.raises(ProviderLaunchError) as captured:
        await provider.result(run_id)
    assert captured.value.code is ProviderErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_native_tool_activity_is_accepted(tmp_path: Path) -> None:
    script = tmp_path / "tool_acp.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialize': out={'protocolVersion':1}\n"
        " elif method == 'session/new': out={'sessionId':'session-1'}\n"
        " elif method == 'session/prompt':\n"
        "  update={'update':{'sessionUpdate':'tool_call','toolCallId':'tool-1'}}\n"
        "  response={'jsonrpc':'2.0','method':'session/update','params':update}\n"
        "  print(json.dumps(response),flush=True)\n"
        "  content={'text':'{\\\"conclusion\\\":\\\"done\\\"}'}\n"
        "  chunk={'update':{'sessionUpdate':'agent_message_chunk','content':content}}\n"
        "  response={'jsonrpc':'2.0','method':'session/update','params':chunk}\n"
        "  print(json.dumps(response),flush=True)\n"
        "  out={}\n"
        " else: out={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(command=sys.executable, args=(str(script),), timeout_seconds=3)
    run_id = await provider.start(request())
    result = await provider.result(run_id)
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.conclusion == "done"


@pytest.mark.asyncio
async def test_permission_requests_are_allowed_once_and_mcp_skip_is_explicit(
    tmp_path: Path,
) -> None:
    script = tmp_path / "permission_acp.py"
    marker = tmp_path / "permission.json"
    script.write_text(
        "import json, os, pathlib, sys\n"
        f"marker=pathlib.Path({str(marker)!r})\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialize':\n"
        "  assert os.environ.get('HERMES_ACP_SKIP_CONFIGURED_MCP') == '1'\n"
        "  out={'protocolVersion':1}\n"
        " elif method == 'session/new': out={'sessionId':'session-1'}\n"
        " elif method == 'session/prompt':\n"
        "  req={'jsonrpc':'2.0','id':'permission-1','method':'session/request_permission',"
        "'params':{'options':[{'optionId':'allow_once','kind':'allow_once','name':'Allow once'},"
        "{'optionId':'deny','kind':'reject_once','name':'Deny'}]}}\n"
        "  print(json.dumps(req),flush=True)\n"
        "  reply=json.loads(sys.stdin.readline())\n"
        "  marker.write_text(json.dumps(reply),encoding='utf-8')\n"
        "  content={'text':'{\\\"conclusion\\\":\\\"tool done\\\"}'}\n"
        "  update={'update':{'sessionUpdate':'agent_message_chunk','content':content}}\n"
        "  event={'jsonrpc':'2.0','method':'session/update','params':update}\n"
        "  print(json.dumps(event),flush=True); out={}\n"
        " else: out={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(
        command=sys.executable,
        args=(str(script),),
        timeout_seconds=3,
        skip_configured_mcp=True,
    )
    run_id = await provider.start(request())
    result = await provider.result(run_id)
    assert result.conclusion == "tool done"
    reply = __import__("json").loads(marker.read_text(encoding="utf-8"))
    assert reply["result"]["outcome"] == {
        "outcome": "selected",
        "optionId": "allow_once",
    }


@pytest.mark.asyncio
async def test_cancel_uses_acp_session_cancel_before_process_fallback(tmp_path: Path) -> None:
    marker = tmp_path / "cancelled.txt"
    ready = tmp_path / "ready.txt"
    script = tmp_path / "cancel_acp.py"
    script.write_text(
        "import json, pathlib, sys\n"
        f"marker=pathlib.Path({str(marker)!r})\n"
        f"ready=pathlib.Path({str(ready)!r})\n"
        "prompt_id=None\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialize': out={'protocolVersion':1}\n"
        " elif method == 'session/new': out={'sessionId':'session-1'}\n"
        " elif method == 'session/prompt':\n"
        "  prompt_id=rid; ready.write_text('ready',encoding='utf-8'); continue\n"
        " elif method == 'session/cancel':\n"
        "  marker.write_text('cancelled',encoding='utf-8')\n"
        "  response={'jsonrpc':'2.0','id':prompt_id,'result':{'stopReason':'cancelled'}}\n"
        "  print(json.dumps(response),flush=True)\n"
        "  continue\n"
        " else: out={}\n"
        " print(json.dumps({'jsonrpc':'2.0','id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(
        command=sys.executable,
        args=(str(script),),
        timeout_seconds=3,
        cancellation_grace_seconds=1,
    )
    run_id = await provider.start(request())
    async with asyncio.timeout(1):
        while not ready.exists():
            await asyncio.sleep(0.01)
    await provider.cancel(run_id)
    result = await provider.result(run_id)
    assert marker.read_text(encoding="utf-8") == "cancelled"
    assert result.outcome is ProviderOutcome.CANCELLED
