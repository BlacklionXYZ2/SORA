"""Opt-in real packaged renderer; control observations and dialogue are labelled fixtures."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
from pathlib import Path

import httpx
import pytest
from tests.desktop.test_foreground import FakeForegroundSource
from tests.runtime.test_companion_presentation import FixtureBridge, PresentationCaller

from sora.api import ApiServerConfig, SoraApiServer
from sora.contracts.embodiment import EmbodimentFeedbackKind, EmbodimentSemanticAction
from sora.providers.mock import DeterministicProvider
from sora.runtime.app_settings import AppSettings, AppSettingsController, SettingsEdit
from sora.runtime.service import RuntimeConfig, SoraRuntime


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_COMPANION_POINT_PLAYER"),
    reason="opt-in packaged companion POINT; fixture controls, not actual native UIA/model",
)
async def test_packaged_point_from_authenticated_dialogue_reports_renderer_lifecycle(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    player = Path(os.environ["SORA_TEST_COMPANION_POINT_PLAYER"]).resolve(strict=True)
    evidence = Path(os.environ.get("SORA_POINT_EVIDENCE_DIR", str(tmp_path))).resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    settings = AppSettingsController(tmp_path / "runtime", AppSettings())
    settings.save(SettingsEdit(version=9, expected_revision=0, changes={
        "perception.window_context": False, "perception.desktop_context": False,
    }))
    runtime = SoraRuntime(
        RuntimeConfig(root=tmp_path / "runtime", identity_root=root / "identity"),
        provider=DeterministicProvider(), app_settings=settings,
        foreground_source=FakeForegroundSource(),
    )
    runtime.windows_bridge = FixtureBridge()  # No Windows UI automation is used in this test.
    await runtime.start()
    settings.provider = PresentationCaller("point")
    server = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token=token))
    unity: asyncio.subprocess.Process | None = None
    try:
        await server.start()
        env = dict(os.environ, SORA_API_TOKEN=token, SORA_CORE_PORT=str(server.actual_port),
            SORA_CORE_PARENT_PID=str(os.getpid()), SORA_EMBODIMENT_DEVICE_ID="device-local",
            SORA_EMBODIMENT_CONNECT_GRANT="", SORA_EMBODIMENT_TOPOLOGY_GRANT="",
            SORA_INTERACTION_EVIDENCE_PATH=str(evidence / "interaction.json"))
        env.pop("SORA_VRM_PATH", None)
        unity = await asyncio.create_subprocess_exec(
            str(player), "-logFile", str(evidence / "player.log"), env=env,
        )
        async with asyncio.timeout(45):
            while runtime.embodiment_state is None or not runtime.embodiment_state.visible:
                assert unity.returncode is None, "QA player exited before connecting"
                await asyncio.sleep(0.1)
        async with httpx.AsyncClient() as client:
            result = await client.post(
                f"http://127.0.0.1:{server.actual_port}/api/v1/dialogue",
                headers={"Authorization": "Bearer " + token},
                json={"content": "Please point at Pause", "request_id": "packaged-point"},
                timeout=10,
            )
        assert result.status_code == 201, result.text
        reply = result.json()["response"]
        assert "not a completed animation" in reply
        command = next(command for command in runtime._embodiment_commands_seen.values()
                       if command.semantic_action is EmbodimentSemanticAction.POINT)
        async with asyncio.timeout(30):
            while not any(event.correlation_id == command.semantic_action_id
                          for event in runtime.embodiment_feedback):
                assert unity.returncode is None, "QA player exited during the point lifecycle"
                await asyncio.sleep(0.1)
        terminal = next(event for event in runtime.embodiment_feedback
                        if event.correlation_id == command.semantic_action_id)
        proof = {
            "dialogue": "deterministic fixture, not an LLM",
            "native_controls": "synthetic fixture, not real Windows UIA",
            "renderer": "actual isolated rebuilt Unity player; procedural rig",
            "reply": reply, "command": command.model_dump(mode="json"),
            "terminal": terminal.model_dump(mode="json"), "visually_reviewed": False,
            "desktop_effect_attempted": False,
        }
        (evidence / "acceptance.json").write_text(json.dumps(proof, indent=2), encoding="utf-8")
        assert terminal.kind is EmbodimentFeedbackKind.COMPLETED, terminal.detail
        assert not await runtime.repository.get_desktop_action(command.semantic_action_id or "")
    finally:
        if unity is not None and unity.returncode is None:
            unity.terminate()
            await asyncio.wait_for(unity.wait(), 10)
        await server.close()
        await runtime.close(drain=False)
