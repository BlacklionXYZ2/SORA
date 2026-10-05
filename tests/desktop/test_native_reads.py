"""Opt-in read-only integration against an owned, non-activating Windows fixture."""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

import httpx
import pytest

from sora.contracts.desktop import DesktopObservationRequest
from sora.desktop.bridge import WindowsObservationBridge

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("SORA_TEST_UIA") != "1", reason="opt-in Windows native reads")
async def test_native_inventory_text_selection_redaction_and_bounds(tmp_path: Path) -> None:
    worker = ROOT / "clients/windows_bridge/bin/Debug/net10.0-windows/windows_bridge.exe"
    fixture = ROOT / "clients/uia_fixture/bin/Debug/net10.0-windows/uia_fixture.exe"
    evidence = tmp_path / "fixture.json"
    process = await asyncio.create_subprocess_exec(str(fixture), str(evidence), "--read-selection")
    bridge = WindowsObservationBridge(worker)
    try:
        async with asyncio.timeout(10):
            while not evidence.exists():
                await asyncio.sleep(0.05)
        before = json.loads(evidence.read_text())
        inventory = await bridge.observe(DesktopObservationRequest(operation="inventory"))
        assert inventory.status == "ok"
        node = next(n for n in inventory.nodes if n.window_handle == before["hwnd"])
        assert node.process_id == process.pid and node.process_started_at is not None
        request = DesktopObservationRequest(
            operation="text", process_id=process.pid, window_handle=before["hwnd"]
        )
        text = await bridge.observe(request)
        assert text.status == "ok", text
        assert text.process_started_at == node.process_started_at
        assert any(n.text == "before" for n in text.nodes)
        assert any(n.selected_text == "bef" and n.selection_available for n in text.nodes)
        assert "never-export-this" not in text.model_dump_json()
        assert all(
            not n.name and not n.text and not n.selected_text for n in text.nodes if n.password
        )
        selection = await bridge.observe(request.model_copy(update={"operation": "selection"}))
        assert selection.status == "ok", selection
        assert any(n.selected_text == "bef" for n in selection.nodes), selection
        bounded = await bridge.observe(request.model_copy(update={"max_text_chars": 3}))
        assert bounded.status == "ok"
        assert sum(len(n.text) + len(n.selected_text) for n in bounded.nodes) <= 3
        assert any(n.text_truncated for n in bounded.nodes)
        # The read helper must not click, type or change the fixture's document.
        after = json.loads(evidence.read_text())
        assert after["press_count"] == after["text_change_count"] == 0
        assert after["text_value"] == before["text_value"] == "before"
        # Optional real local-model/Core pass against a separately launched isolated QA state.
        endpoint = os.getenv("SORA_TEST_READ_API")
        if endpoint:
            assert urlparse(endpoint).hostname in {"127.0.0.1", "localhost", "::1"}
            token = Path(os.environ["SORA_TEST_READ_TOKEN_FILE"]).read_text().strip()
            async with httpx.AsyncClient(timeout=95, trust_env=False) as client:
                reply = await client.post(
                    endpoint + "/api/v1/dialogue",
                    headers={"Authorization": "Bearer " + token},
                    json={
                        "content": "Read the currently selected text in the window titled "
                        "SORA UIA acceptance fixture using native Windows text, not a screenshot."
                    },
                )
            assert reply.status_code == 201, reply.text
            answer = reply.json()["response"]
            assert "inspect_window (selection)" in answer or "inspect_window (text)" in answer, (
                answer
            )
            assert re.search(r"\bbef\b", answer), answer
            assert "no text currently selected" not in answer.lower(), answer
            final = json.loads(evidence.read_text())
            assert final["press_count"] == final["text_change_count"] == 0
            assert final["text_value"] == "before"
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()
