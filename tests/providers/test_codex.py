from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, ProviderOutcome, ProviderRequest
from sora.providers.base import ProviderLaunchError
from sora.providers.codex import CodexAppServerProvider, parse_codex_result
from sora.workspaces import GitWorkspaceManager


def request(*, run_id: str = "run-1") -> ProviderRequest:
    from datetime import UTC, datetime, timedelta

    return ProviderRequest(
        request_id=f"request-{run_id}",
        task_id="task-1",
        run_id=run_id,
        owner_id="owner-local",
        project_id="project-sora",
        intent="Inspect the task",
        context="AUTHORITATIVE_STATE\nFACT: existing",
        context_manifest_ref="context-1",
        deadline=datetime.now(UTC) + timedelta(seconds=10),
        artifact_destination="C:/tmp/artifacts",
        idempotency_key=f"provider-start-{run_id}",
    )


def test_codex_json_result_is_normalized_into_a_patch() -> None:
    result = parse_codex_result(
        '{"conclusion":"done","facts":["candidate"],"memory_updates":[]}',
        request(),
    )
    assert result.outcome is ProviderOutcome.COMPLETED
    assert result.patch is not None
    operation = result.patch.operations[0]
    assert operation.operation == "propose_fact"
    assert operation.fact.epistemic_status == "inference"
    assert operation.fact.confidence == 0.5


@pytest.mark.asyncio
async def test_missing_codex_executable_is_typed_unavailable(tmp_path: Path) -> None:
    provider = CodexAppServerProvider(
        command=str(tmp_path / "missing-codex.exe"),
        cwd=str(tmp_path),
    )
    with pytest.raises(ProviderLaunchError) as captured:
        await provider.start(request())
    assert captured.value.code is ProviderErrorCode.UNAVAILABLE


def test_codex_rejects_unowned_or_uncontained_write_modes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="owned workspace"):
        CodexAppServerProvider(cwd=str(tmp_path), sandbox="workspace-write")
    with pytest.raises(ValueError, match="danger-full-access"):
        CodexAppServerProvider(cwd=str(tmp_path), sandbox="danger-full-access")


@pytest.mark.asyncio
async def test_codex_write_requires_matching_live_workspace_reference(tmp_path: Path) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    setup_commands: tuple[tuple[str, ...], ...] = (
        ("init",),
        ("config", "user.email", "sora-tests@example.invalid"),
        ("config", "user.name", "SORA Tests"),
    )
    for args in setup_commands:
        process = await asyncio.create_subprocess_exec("git", *args, cwd=repository)
        assert await process.wait() == 0
    (repository / "file.txt").write_text("base\n", encoding="utf-8")
    commit_commands: tuple[tuple[str, ...], ...] = (
        ("add", "file.txt"),
        ("commit", "-m", "base"),
    )
    for args in commit_commands:
        process = await asyncio.create_subprocess_exec("git", *args, cwd=repository)
        assert await process.wait() == 0

    manager = GitWorkspaceManager(tmp_path / "state")
    record = manager.allocate(
        repository,
        workspace_id="workspace-1",
        task_id="task-1",
        base_ref="HEAD",
        lease_owner="worker-1",
        lease_seconds=60,
    )
    provider = CodexAppServerProvider(
        cwd=str(record.worktree_path),
        sandbox="workspace-write",
        workspace_record=record,
        workspace_manager=manager,
        lease_owner="worker-1",
    )
    mismatched = request().model_copy(update={"workspace_ref": "workspace-other"})
    with pytest.raises(ProviderLaunchError, match="workspace_ref") as captured:
        await provider.start(mismatched)
    assert captured.value.code is ProviderErrorCode.INVALID_REQUEST


@pytest.mark.asyncio
async def test_fake_app_server_supports_models_start_result_and_resume(tmp_path: Path) -> None:
    script = tmp_path / "fake_codex.py"
    script.write_text(
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialized': continue\n"
        " if method == 'initialize': out={'userAgent':'fake','platformFamily':'windows'}\n"
        " elif method == 'model/list':\n"
        "  out={'data':[{'id':'gpt-5.6-luna','model':'gpt-5.6-luna',"
        "'displayName':'GPT-5.6 Luna','isDefault':False}]}\n"
        " elif method in {'thread/start','thread/resume'}:\n"
        "  out={'thread':{'id':m.get('params',{}).get('threadId','thread-1')}}\n"
        " elif method == 'turn/start':\n"
        "  out={'turn':{'id':'turn-1','status':'inProgress','items':[]}}\n"
        "  print(json.dumps({'id':rid,'result':out}),flush=True)\n"
        "  item={'type':'agentMessage','id':'item-1','text':"
        '\'{\\"conclusion\\":\\"inspected\\",\\"facts\\":[]}\'}\n'
        "  params={'threadId':'thread-1','turnId':'turn-1','item':item}\n"
        "  print(json.dumps({'method':'item/completed','params':params}),flush=True)\n"
        "  turn={'id':'turn-1','status':'completed','items':[item]}\n"
        "  print(json.dumps({'method':'turn/completed','params':"
        "{'threadId':'thread-1','turn':turn}}),flush=True)\n"
        "  continue\n"
        " else: out={}\n"
        " print(json.dumps({'id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = CodexAppServerProvider(
        command=sys.executable,
        args=(str(script),),
        cwd=str(tmp_path),
        timeout_seconds=3,
    )
    capabilities = await provider.capabilities()
    assert capabilities.sessions
    assert capabilities.resume
    assert capabilities.steer
    assert capabilities.cancel
    assert capabilities.tool_restrictions
    models = await provider.available_models()
    assert models[0]["model"] == "gpt-5.6-luna"

    run_id = await provider.start(request())
    assert await provider.start(request()) == run_id
    result = await provider.result(run_id)
    assert result.conclusion == "inspected"
    thread_id = await provider.session_id(run_id)
    assert thread_id == "thread-1"

    resumed_id = await provider.resume(thread_id, request(run_id="run-2"))
    resumed = await provider.result(resumed_id)
    assert resumed.conclusion == "inspected"
    assert await provider.session_id(resumed_id) == thread_id


@pytest.mark.asyncio
async def test_cancel_sends_turn_interrupt_and_reconciles_interrupted(tmp_path: Path) -> None:
    marker = tmp_path / "interrupted.txt"
    ready = tmp_path / "ready.txt"
    script = tmp_path / "cancel_codex.py"
    script.write_text(
        "import json, pathlib, sys\n"
        f"marker=pathlib.Path({str(marker)!r}); ready=pathlib.Path({str(ready)!r})\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialized': continue\n"
        " if method == 'initialize': out={}\n"
        " elif method == 'thread/start': out={'thread':{'id':'thread-1'}}\n"
        " elif method == 'turn/start':\n"
        "  out={'turn':{'id':'turn-1','status':'inProgress','items':[]}}\n"
        "  print(json.dumps({'id':rid,'result':out}),flush=True)\n"
        "  ready.write_text('ready',encoding='utf-8'); continue\n"
        " elif method == 'turn/interrupt':\n"
        "  marker.write_text('interrupted',encoding='utf-8')\n"
        "  print(json.dumps({'id':rid,'result':{}}),flush=True)\n"
        "  turn={'id':'turn-1','status':'interrupted','items':[]}\n"
        "  event={'method':'turn/completed','params':{'threadId':'thread-1','turn':turn}}\n"
        "  print(json.dumps(event),flush=True); continue\n"
        " else: out={}\n"
        " print(json.dumps({'id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = CodexAppServerProvider(
        command=sys.executable,
        args=(str(script),),
        cwd=str(tmp_path),
        timeout_seconds=3,
    )
    run_id = await provider.start(request())
    async with asyncio.timeout(1):
        while not ready.exists():
            await asyncio.sleep(0.01)
    await provider.cancel(run_id)
    result = await provider.result(run_id)
    assert result.outcome is ProviderOutcome.CANCELLED
    assert marker.read_text(encoding="utf-8") == "interrupted"
