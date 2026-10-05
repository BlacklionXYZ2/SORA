"""No-inference native Codex command boundary probe in a fresh local QA directory."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sora.contracts.models import ProviderRequest
from sora.providers.codex import CodexAppServerProvider, _Run


async def main() -> None:
    state = Path(sys.argv[1]).resolve()
    repository = Path(__file__).resolve().parents[1]
    if repository not in state.parents or ".local" not in state.parts or state.exists():
        raise ValueError("Use a fresh QA directory beneath SORA/.local")
    project = state / "project"
    outside = state / "outside.txt"
    project.mkdir(parents=True)
    outside.write_text("preserved outside marker\n", encoding="utf-8")
    outside_directory = state / "outside-directory"
    outside_directory.mkdir()
    junction = project / "outside-junction"
    if os.name == "nt":
        import subprocess

        subprocess.run(
            [shutil.which("powershell.exe") or "powershell.exe", "-NoProfile", "-Command",
             f"New-Item -ItemType Junction -Path '{junction}' -Target '{outside_directory}' "
             "| Out-Null"],
            check=True,
        )
    provider = CodexAppServerProvider(cwd=str(project))
    process = await asyncio.create_subprocess_exec(
        shutil.which("codex") or "codex",
        "app-server",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        cwd=project,
        limit=4194304,
    )
    request = ProviderRequest(
        request_id="boundary-probe",
        task_id="boundary-probe",
        run_id="boundary-probe",
        owner_id="owner-local",
        project_id="qa",
        intent="No inference boundary probe",
        context="QA fixture only",
        context_manifest_ref="qa",
        deadline=datetime.now(UTC) + timedelta(seconds=60),
        artifact_destination=str(state),
        idempotency_key="boundary-probe",
    )
    session = _Run(process, request)
    results: dict[str, object] = {}
    policy = {
        "type": "workspaceWrite",
        "writableRoots": [str(project)],
        "networkAccess": False,
        "excludeTmpdirEnvVar": True,
        "excludeSlashTmp": True,
    }
    try:
        await provider._initialize(session)
        config = await provider._rpc(session, "config/read", {"includeLayers": False})
        servers = (config.get("config") or {}).get("mcp_servers", {})
        results["configured_mcp_count"] = len(servers)
        overrides = {
            "features.apps": False,
            "features.multi_agent": False,
            "features.multi_agent_v2": False, "features.plugins": False,
            "features.remote_plugin": False, "features.browser_use": False,
            "features.browser_use_external": False,
            "features.browser_use_full_cdp_access": False,
            "features.in_app_browser": False,
            "web_search": "disabled",
            **{f"mcp_servers.{name}.enabled": False for name in servers},
        }
        thread = await provider._rpc(
            session,
            "thread/start",
            {
                "cwd": str(project),
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
                "config": overrides,
                "model": "gpt-5.6-luna",
                "serviceName": "sora-boundary-qa",
            },
        )
        results["thread_config_accepted"] = bool((thread.get("thread") or {}).get("id"))
        commands = {
            "inside_write": "Set-Content -LiteralPath 'inside.txt' -Value 'inside'",
            "outside_write": f"Set-Content -LiteralPath '{str(outside)}' -Value 'BAD'",
            "outside_read": f"Get-Content -LiteralPath '{str(outside)}'",
            "junction_write": (
                "Set-Content -LiteralPath 'outside-junction/escaped.txt' -Value 'BAD'"
            ),
        }
        for name, code in commands.items():
            response = await provider._rpc(
                session,
                "command/exec",
                {
                    "command": [
                        shutil.which("powershell.exe") or "powershell.exe",
                        "-NoProfile",
                        "-NonInteractive",
                        "-Command",
                        "$ErrorActionPreference='Stop';" + code,
                    ],
                    "cwd": str(project),
                    "sandboxPolicy": policy,
                    "timeoutMs": 10000,
                },
            )
            results[name] = {key: response.get(key) for key in ("exitCode", "stdout", "stderr")}
        results["inside_exists"] = (project / "inside.txt").exists()
        results["outside_preserved"] = outside.read_text() == "preserved outside marker\n"
        results["junction_target_preserved"] = not (outside_directory / "escaped.txt").exists()
        readonly = await provider._rpc(session, "command/exec", {
            "command": [shutil.which("powershell.exe") or "powershell.exe", "-NoProfile",
                        "-NonInteractive", "-Command",
                        "$ErrorActionPreference='Stop';Set-Content -LiteralPath 'readonly.txt' "
                        "-Value 'BAD'"],
            "cwd": str(project), "sandboxPolicy": {"type": "readOnly"}, "timeoutMs": 10000,
        })
        results["readonly_write"] = {
            key: readonly.get(key) for key in ("exitCode", "stdout", "stderr")
        }
        results["readonly_preserved"] = not (project / "readonly.txt").exists()
        results["inference_started"] = False
    finally:
        await provider._stop_process(process)
        (state / "boundary-proof.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
    assert results["inside_exists"] and results["outside_preserved"]
    assert results["junction_target_preserved"] and results["readonly_preserved"]


if __name__ == "__main__":
    asyncio.run(main())
