from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.providers.test_codex import request

from sora.contracts.models import ProviderErrorCode
from sora.providers.antigravity import AntigravityProvider
from sora.providers.base import ProviderLaunchError
from sora.providers.codex import CodexAppServerProvider
from sora.providers.hermes import HermesACPProvider


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_cursor", [False, True])
async def test_codex_pagination_and_exact_turn_selection(tmp_path: Path, bad_cursor: bool) -> None:
    script = tmp_path / "codex.py"
    script.write_text(
        "import json,sys\n"
        f"bad_cursor={bad_cursor!r}\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); p=m.get('params',{}); rid=m.get('id')\n"
        " if method=='initialized': continue\n"
        " if method=='initialize': out={}\n"
        " elif method=='model/list':\n"
        "  assert p['includeHidden'] is True\n"
        "  out={'data':[{'model':'m2' if p.get('cursor') else 'm1'}],"
        "'nextCursor':'page2' if bad_cursor or not p.get('cursor') else None}\n"
        " elif method in {'thread/start','thread/resume'}:\n"
        "  assert p['model']=='exact/model'; out={'thread':{'id':'t'},'model':'exact/model'}\n"
        " elif method=='turn/start':\n"
        "  assert p['model']=='exact/model' and p['effort']=='high'\n"
        "  print(json.dumps({'id':rid,'result':{'turn':{'id':'turn'}}}),flush=True)\n"
        "  item={'type':'agentMessage','id':'i',"
        "'text':json.dumps({'conclusion':'selected correctly'})}\n"
        "  print(json.dumps({'method':'item/completed','params':{"
        "'threadId':'t','turnId':'turn','item':item}}),flush=True)\n"
        "  print(json.dumps({'method':'turn/completed','params':{'threadId':'t',"
        "'turn':{'id':'turn','status':'completed','items':[{'type':'agentMessage','id':'i',"
        "'text':json.dumps({'conclusion':'selected correctly'})}]}}}),flush=True); continue\n"
        " else: raise AssertionError(method)\n"
        " print(json.dumps({'id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = CodexAppServerProvider(
        command=sys.executable, args=(str(script),), cwd=str(tmp_path), timeout_seconds=2
    )
    if bad_cursor:
        with pytest.raises(ValueError, match="cursor"):
            await provider.available_models()
        return
    assert [entry["model"] for entry in await provider.available_models()] == ["m1", "m2"]
    selected = request().model_copy(update={"model": "exact/model", "reasoning_effort": "high"})
    assert (
        await provider.result(await provider.start(selected))
    ).conclusion == "selected correctly"
    resumed = selected.model_copy(update={"run_id": "resumed", "request_id": "resumed"})
    assert (
        await provider.result(await provider.resume("t", resumed))
    ).conclusion == "selected correctly"
    assert provider.model == "gpt-5.6-luna"
    assert provider.reasoning_effort == "low"


@pytest.mark.asyncio
@pytest.mark.parametrize("reject", [False, True])
async def test_hermes_discovery_and_session_switch_before_prompt(
    tmp_path: Path, reject: bool
) -> None:
    script = tmp_path / "hermes.py"
    script.write_text(
        "import json,sys,os\n"
        f"reject={reject!r}\n"
        "selected=False; metadata=False\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); p=m.get('params',{}); rid=m.get('id')\n"
        " if method=='initialize':\n"
        "  metadata=p['clientInfo']['name']=='sora-catalogue'\n"
        "  if metadata: assert os.environ['HERMES_ACP_SKIP_CONFIGURED_MCP']=='1'\n"
        "  out={'protocolVersion':1}\n"
        " elif method=='session/new': out={'sessionId':'s','models':{'availableModels':["
        "{'modelId':'openai:gpt-6-luna','name':'GPT-6 Luna','description':'Fast specialist'}]}}\n"
        " elif method=='session/load': out={}\n"
        " elif method=='session/set_model':\n"
        "  assert p['modelId']=='openai:gpt-6-luna' and p['sessionId']=='s'\n"
        "  if reject:\n"
        "   print(json.dumps({'id':rid,'error':{'message':'invalid model SECRET'}}),"
        "flush=True); continue\n"
        "  selected=True; out={}\n"
        " elif method=='session/prompt':\n"
        "  assert not metadata and selected\n"
        "  print(json.dumps({'method':'session/update','params':{'update':{"
        "'sessionUpdate':'agent_message_chunk','content':{"
        "'text':json.dumps({'conclusion':'right model'})}}}}),flush=True)\n"
        "  out={}\n"
        " else: raise AssertionError(method)\n"
        " print(json.dumps({'id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    provider = HermesACPProvider(command=sys.executable, args=(str(script),), timeout_seconds=2)
    assert (await provider.available_models())[0]["model"] == "openai:gpt-6-luna"
    selected = request().model_copy(update={"model": "openai:gpt-6-luna"})
    run = await provider.start(selected)
    if reject:
        with pytest.raises(ProviderLaunchError, match="no prompt") as captured:
            await provider.result(run)
        assert captured.value.code is ProviderErrorCode.INVALID_REQUEST
    else:
        assert (await provider.result(run)).conclusion == "right model"
        resumed = selected.model_copy(update={"run_id": "resumed", "request_id": "resumed"})
        assert (
            await provider.result(await provider.resume("s", resumed))
        ).conclusion == "right model"
    with pytest.raises(ProviderLaunchError, match="effort"):
        await provider.start(
            selected.model_copy(update={"run_id": "effort", "reasoning_effort": "low"})
        )


@pytest.mark.asyncio
async def test_antigravity_exact_tier_and_conflict(tmp_path: Path) -> None:
    script = tmp_path / "antigravity.py"
    script.write_text(
        "import json,sys\n"
        "args=sys.argv[1:]\n"
        "assert args[args.index('--model')+1]=='gemini-3.8-flash-low'\n"
        "assert '--effort' not in args\n"
        "print(json.dumps({'conclusion':'correct tier'}))\n",
        encoding="utf-8",
    )
    provider = AntigravityProvider(command=sys.executable, args=(str(script),), cwd=str(tmp_path))
    selected = request().model_copy(update={"model": "gemini-3.8-flash-low"})
    result = await provider.result(await provider.start(selected))
    assert result.conclusion is not None and "correct tier" in result.conclusion
    with pytest.raises(ProviderLaunchError, match="different effort"):
        await provider.start(
            selected.model_copy(update={"run_id": "conflict", "reasoning_effort": "high"})
        )


@pytest.mark.asyncio
async def test_antigravity_catalogue_drains_all_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "models.py"
    script.write_text(
        "import time\nprint('Fetching available models...',flush=True)\n"
        "print('gemini-3.8-flash-high\\tGemini 3.8 Flash (High)',flush=True)\n"
        "time.sleep(.05)\nprint('gemini-3.8-flash-low\\tGemini 3.8 Flash (Low)',flush=True)\n",
        encoding="utf-8",
    )
    spawn = asyncio.create_subprocess_exec

    async def wrapped(*args: str, **kwargs: Any) -> asyncio.subprocess.Process:
        assert args[1:] == ("models",)
        return await spawn(sys.executable, str(script), **kwargs)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", wrapped)
    provider = AntigravityProvider(command="agy", cwd=str(tmp_path))
    assert [model["model"] for model in await provider.available_models()] == [
        "gemini-3.8-flash-high",
        "gemini-3.8-flash-low",
    ]
