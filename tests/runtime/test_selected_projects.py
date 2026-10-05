from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from sora.api.protocol import HttpRequest
from sora.api.routes import RouteHandler
from sora.contracts.models import TaskStatus
from sora.providers.codex import CodexAppServerProvider
from sora.providers.windows_job import process_may_be_alive
from sora.runtime.app_settings import AppSettings, AppSettingsController
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.security.local_policy import owner_local_scope
from tests.runtime.test_coding_workspaces import fake_app_server, repository

IDENTITY = Path(__file__).resolve().parents[2] / "identity"


@pytest.mark.asyncio
async def test_direct_project_persisted_dirty_files_preserved_and_release(tmp_path: Path) -> None:
    project = repository(tmp_path)
    (project / "owner-dirty.txt").write_text("owner change")
    script = fake_app_server(tmp_path)
    provider = CodexAppServerProvider(
        command=str(Path(sys.base_prefix) / "python.exe"),
        args=(str(script),),
        cwd=str(tmp_path),
        timeout_seconds=5,
    )
    state = tmp_path / "state"
    runtime = SoraRuntime(
        RuntimeConfig(root=state, identity_root=IDENTITY, worker_count=1),
        providers={"codex": provider},
        app_settings=AppSettingsController(state, AppSettings()),
    )
    await runtime.start()
    try:
        with owner_local_scope():
            with pytest.raises(ValueError, match="Which project"):
                await runtime.submit_task("Edit file module.py", explicit_provider="codex")
            receipt = await runtime.submit_task(
                "Edit file module.py to implement the marker change and test it.",
                working_directory=str(project),
                workspace_mode="direct",
            )
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=10)
        assert report.status is TaskStatus.COMPLETED and report.result is not None
        assert "after" in (project / "module.py").read_text()
        assert (project / "owner-dirty.txt").read_text() == "owner change"
        assert receipt.task.working_directory == str(project.resolve())
        handler = RouteHandler(runtime)
        remote = await handler.handle_request(
            HttpRequest(
                method="GET",
                path=f"/api/v1/tasks/{receipt.task.task_id}",
                headers={},
                body=b"",
            ),
            remote_scopes=frozenset({"tasks:read"}),
        )
        import json

        assert "working_directory" not in json.loads(remote.body)
        denied = await handler.handle_request(
            HttpRequest(
                method="GET",
                path="/api/v1/paths",
                headers={},
                body=b"",
            ),
            remote_scopes=frozenset({"tasks:read"}),
        )
        assert denied.status_code == 403
        replay = await handler.handle_request(
            HttpRequest(method="GET", path="/api/v1/events?since_sequence=999999",
                        headers={}, body=b""),
            remote_scopes=frozenset({"events:read"}),
        )
        remote_snapshot = json.loads(replay.body)["snapshot"]
        assert "working_directory" not in remote_snapshot["tasks"][0]
        assert any("changelog missing" in warning.lower() for warning in report.result.warnings)
        for _ in range(100):
            if not (await runtime.project_paths.projection())["leases"]:
                break
            await asyncio.sleep(0.02)
        assert not (await runtime.project_paths.projection())["leases"]
        events = (await runtime.project_paths.projection())["events"]
        assert any(
            event["source"] == "filesystem_diff" and event["operation"] == "file.changed"
            for event in events
        )
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_cancel_bound_stubborn_writer_reaps_child_before_release(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    script = tmp_path / "held_server.py"
    real_python = str(Path(sys.base_prefix) / "python.exe")
    child_code = (
        "import pathlib,time;\n"
        "while True:\n pathlib.Path('heartbeat.txt').write_text(str(time.time()));time.sleep(.05)"
    )
    script.write_text(
        "import sys,json,subprocess,pathlib,time\n"
        "for line in sys.stdin:\n"
        " m=json.loads(line); method=m.get('method'); rid=m.get('id')\n"
        " with open('methods.log','a') as log:log.write(str(time.time())+' '+str(method)+'\\n')\n"
        " if method=='initialized':continue\n"
        " if method=='thread/start':out={'thread':{'id':'held'}}\n"
        " elif method=='turn/start':\n"
        "  child_log=open('child-output.log','w')\n"
        f"  child=subprocess.Popen([{real_python!r},'-c',{child_code!r}],"
        "stdin=subprocess.DEVNULL,stdout=child_log,stderr=child_log)\n"
        "  pathlib.Path('child.pid').write_text(str(child.pid))\n"
        "  out={'turn':{'id':'stubborn'}}\n"
        " else:out={}\n"
        " if rid is not None:print(json.dumps({'id':rid,'result':out}),flush=True)\n",
    )
    provider = CodexAppServerProvider(
        command=real_python, args=(str(script),), cwd=str(tmp_path), timeout_seconds=20
    )
    state = tmp_path / "state"
    runtime = SoraRuntime(
        RuntimeConfig(root=state, identity_root=IDENTITY),
        providers={"codex": provider},
        app_settings=AppSettingsController(state, AppSettings()),
    )
    await runtime.start()
    try:
        with owner_local_scope():
            receipt = await runtime.submit_task(
                "Edit only the test fixture",
                explicit_provider="codex",
                working_directory=str(project),
                workspace_mode="direct",
            )
        for _ in range(500):
            if (project / "heartbeat.txt").exists():
                break
            await asyncio.sleep(0.02)
        assert (project / "heartbeat.txt").exists(), (
            (project / "methods.log").read_text()
            + "\n" + (project / "child-output.log").read_text()
            if (project / "methods.log").exists()
            else str(await runtime.runtime_repository.get_task(receipt.task.task_id))
        )
        child_pid = int((project / "child.pid").read_text())
        assert process_may_be_alive(child_pid)
        assert await runtime.cancel(receipt.task.task_id)
        report = await runtime.wait_for_task(receipt.task.task_id, timeout=10)
        assert report.status is TaskStatus.CANCELLED
        for _ in range(100):
            if not (await runtime.project_paths.projection())["leases"]:
                break
            await asyncio.sleep(0.02)
        assert not process_may_be_alive(child_pid)
        assert not (await runtime.project_paths.projection())["leases"]
        timestamp = (project / "heartbeat.txt").stat().st_mtime_ns
        await asyncio.sleep(0.1)
        assert (project / "heartbeat.txt").stat().st_mtime_ns == timestamp
    finally:
        await runtime.close()
