from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sora.contracts.models import ProviderErrorCode, TaskStatus
from sora.providers.base import ProviderLaunchError
from sora.providers.codex import CodexAppServerProvider
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def repository(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init")
    git(source, "config", "user.email", "sora-tests@example.invalid")
    git(source, "config", "user.name", "SORA Tests")
    (source / "module.py").write_text(
        'def marker() -> str:\n    return "before"\n',
        encoding="utf-8",
    )
    (source / "verify.py").write_text(
        'from module import marker\nassert marker() == "after"\n',
        encoding="utf-8",
    )
    git(source, "add", "module.py", "verify.py")
    git(source, "commit", "-m", "fixture base")
    return source


def fake_app_server(tmp_path: Path) -> Path:
    script = tmp_path / "fake_codex_write.py"
    script.write_text(
        "import json, pathlib, subprocess, sys\n"
        "sandbox = None\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " if method == 'initialized': continue\n"
        " if method == 'initialize': out={}\n"
        " elif method == 'thread/start':\n"
        "  sandbox=m.get('params',{}).get('sandbox')\n"
        "  out={'thread':{'id':'thread-managed-1'}}\n"
        " elif method == 'turn/start':\n"
        "  assert sandbox == 'workspace-write'\n"
        "  target=pathlib.Path('module.py')\n"
        "  target.write_text(target.read_text(encoding='utf-8').replace('before','after'),"
        "encoding='utf-8')\n"
        "  check=subprocess.run([sys.executable,'-B','verify.py'],capture_output=True,text=True)\n"
        "  assert check.returncode == 0, check.stderr\n"
        "  out={'turn':{'id':'turn-managed-1','status':'inProgress','items':[]}}\n"
        "  print(json.dumps({'id':rid,'result':out}),flush=True)\n"
        "  body={'conclusion':'isolated change verified','facts':[],"
        "'files_changed':['module.py'],'commands_run':['python -B verify.py'],"
        "'uncertainties':[],'warnings':[]}\n"
        "  item={'type':'agentMessage','id':'item-1','text':json.dumps(body)}\n"
        "  params={'threadId':'thread-managed-1','turnId':'turn-managed-1','item':item}\n"
        "  print(json.dumps({'method':'item/completed','params':params}),flush=True)\n"
        "  turn={'id':'turn-managed-1','status':'completed','items':[item]}\n"
        "  print(json.dumps({'method':'turn/completed','params':"
        "{'threadId':'thread-managed-1','turn':turn}}),flush=True)\n"
        "  continue\n"
        " else: out={}\n"
        " print(json.dumps({'id':rid,'result':out}),flush=True)\n",
        encoding="utf-8",
    )
    return script


@pytest.mark.asyncio
async def test_p06_coding_route_allocates_codex_worktree_and_captures_artifact(
    tmp_path: Path,
) -> None:
    source = repository(tmp_path)
    script = fake_app_server(tmp_path)
    provider = CodexAppServerProvider(
        command=sys.executable,
        args=(str(script),),
        cwd=str(source),
        timeout_seconds=5,
    )
    workspace_root = tmp_path / "workspace-state"
    runtime = SoraRuntime(
        RuntimeConfig(
            root=tmp_path / "runtime",
            identity_root=IDENTITY_ROOT,
            worker_count=1,
            task_timeout_seconds=5,
            coding_repository_root=source,
            coding_workspace_root=workspace_root,
            coding_base_ref="HEAD",
        ),
        providers={"codex": provider, "deterministic": DeterministicProvider()},
    )
    await runtime.start()

    receipt = await runtime.submit_task(
        "Edit file module.py to implement the marker change and test it."
    )
    report = await runtime.wait_for_task(receipt.task.task_id, timeout=10)

    assert report.status is TaskStatus.COMPLETED
    assert report.result is not None
    assert report.result.conclusion == "isolated change verified"
    assert (source / "module.py").read_text("utf-8").endswith('return "before"\n')
    workspace_id = f"workspace-{receipt.run.run_id}"
    record_path = workspace_root / "records" / f"{workspace_id}.json"
    record = json.loads(record_path.read_text("utf-8"))
    worktree = Path(record["worktree_path"])
    assert (worktree / "module.py").read_text("utf-8").endswith('return "after"\n')
    artifact_path = workspace_root / "artifacts" / workspace_id / "coding-run.json"
    artifact = json.loads(artifact_path.read_text("utf-8"))
    assert artifact["provider"] == "codex-app-server"
    assert artifact["workspace"]["changed_files"] == ["module.py"]
    assert artifact["verification_commands"] == ["python -B verify.py"]
    assert '-    return "before"' in artifact["workspace"]["diff"]
    assert '+    return "after"' in artifact["workspace"]["diff"]
    assert not (workspace_root / "leases" / f"{workspace_id}.json").exists()
    assert any(item.startswith("review_artifact:") for item in report.result.task_updates)
    traces = await runtime.runtime_repository.traces(receipt.task.task_id)
    phases = {trace.phase for trace in traces}
    assert {
        "routing.selected",
        "workspace.allocated",
        "workspace.artifact_captured",
        "workspace.lease_released",
        "session.attached",
    } <= phases
    await runtime.close()


@pytest.mark.asyncio
async def test_runtime_rejects_coding_write_before_submission_without_workspace(
    tmp_path: Path,
) -> None:
    provider = CodexAppServerProvider(command="not-launched", cwd=str(tmp_path))
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=IDENTITY_ROOT),
        providers={"codex": provider},
    )
    await runtime.start()
    with pytest.raises(ProviderLaunchError) as captured:
        await runtime.submit_task(
            "Edit file module.py to implement a change.",
            explicit_provider="codex",
        )
    assert captured.value.code is ProviderErrorCode.INVALID_REQUEST
    assert await runtime.runtime_repository.list_tasks() == []
    await runtime.close()
