"""Opt-in actual C# ↔ Python loopback transport acceptance; no model or UI calls."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from tests.authorization_helpers import persist_operation_grant

from sora.api import ApiServerConfig, SoraApiServer
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime


@pytest.mark.asyncio
@pytest.mark.skipif(os.environ.get("SORA_TEST_CSHARP") != "1", reason="opt-in .NET SDK probe")
async def test_actual_csharp_transport(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path, identity_root=root / "identity"),
        provider=DeterministicProvider(),
    )
    await runtime.start()
    token = "synthetic-p09-probe-token-123456"
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token=token))
    try:
        for action in ("connect", "command", "topology"):
            await persist_operation_grant(
                runtime, f"embodiment.{action}", grant_id=f"grant-{action}"
            )
        await server.start()
        env = dict(os.environ, SORA_PROBE_TOKEN=token)
        process = await asyncio.create_subprocess_exec(
            "dotnet",
            "run",
            "--no-build",
            "--project",
            str(root / "clients/protocol_probe"),
            "--",
            str(server.actual_port),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 25)
        except BaseException:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        assert process.returncode == 0, (stdout.decode(), stderr.decode())
        assert "PASS:" in stdout.decode()
        for _ in range(100):
            if not runtime.get_embodiment_projection()["connected"]:
                break
            await asyncio.sleep(0.01)
        assert not runtime.get_embodiment_projection()["connected"]
        assert runtime.embodiment_state is None
        # Closing the rendering client must not close the Core.
        assert server.is_serving
    finally:
        await server.close()
        await runtime.close()
