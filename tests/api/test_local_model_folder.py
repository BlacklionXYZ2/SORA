"""Owner-only LM Studio folder discovery and restart-staged model selection."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from sora.api.protocol import HttpRequest
from sora.api.remote import required_remote_scope
from sora.api.routes import RouteHandler
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


class FakeLmsProcess:
    returncode = 0

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows

    async def communicate(self) -> tuple[bytes, bytes]:
        return json.dumps(self.rows).encode(), b""


@pytest.mark.asyncio
async def test_owner_scans_indexed_files_in_selected_folder_and_stages_choice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = tmp_path / "LM Models"
    model_file = folder / "publisher" / "model" / "vision.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"GGUF-fixture")
    key = "publisher/model/vision"
    rows: list[dict[str, object]] = [
        {"type": "llm", "modelKey": key, "displayName": "Vision fixture",
         "path": "publisher/model/vision.gguf", "vision": True},
        {"type": "llm", "modelKey": "other/model", "displayName": "Elsewhere",
         "path": "other/model.gguf"},
        {"type": "embedding", "modelKey": "embedding", "path": "embedding.gguf"},
        {"type": "llm", "modelKey": "escape", "path": "../escape.gguf"},
    ]

    async def fake_exec(*_: object, **__: object) -> FakeLmsProcess:
        return FakeLmsProcess(rows)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    root = tmp_path / "core"
    runtime = SoraRuntime(RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
                          provider=DeterministicProvider())
    await runtime.start()
    try:
        route = RouteHandler(runtime)
        request = HttpRequest("POST", "/api/v1/models/scan", {},
                              json.dumps({"folder": str(folder)}).encode())
        denied = await route.handle_request(request, remote_scopes=frozenset())
        assert denied.status_code == 403
        response = await route.handle_request(request)
        assert response.status_code == 200
        data = json.loads(response.body)
        assert data["count"] == 1
        assert data["models"] == [{
            "model_key": key, "display_name": "Vision fixture",
            "relative_path": "publisher/model/vision.gguf",
            "size_bytes": len(b"GGUF-fixture"), "vision": True,
        }]
        settings = {
            "version": 1, "expected_revision": 0,
            "dialogue_backend": "openai-compatible",
            "dialogue_model": key,
            "dialogue_model_folder": str(folder),
            "dialogue_base_url": "http://127.0.0.1:1234/v1",
            "dialogue_timeout_seconds": 30, "worker_count": 2,
            "context_max_chars": 8000,
        }
        invalid = await route.handle_request(HttpRequest(
            "POST", "/api/v1/settings", {},
            json.dumps({**settings, "dialogue_model": "not-in-folder"}).encode(),
        ))
        assert invalid.status_code == 422
        saved = await route.handle_request(HttpRequest(
            "POST", "/api/v1/settings", {}, json.dumps(settings).encode(),
        ))
        assert saved.status_code == 200
        assert json.loads(saved.body)["restart_required"] is True
        projection = await route.handle_request(HttpRequest(
            "GET", "/api/v1/projections/settings", {}, b"",
        ))
        pending = json.loads(projection.body)["pending_settings"]
        assert pending["dialogue_model_folder"] == str(folder)
    finally:
        await runtime.close()

    restarted = SoraRuntime(RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
                            provider=DeterministicProvider())
    await restarted.start()
    try:
        assert restarted.config.dialogue_model == key
        assert restarted.config.dialogue_model_folder == folder
        assert restarted.active_settings_revision == 1
    finally:
        await restarted.close()


def test_model_folder_scan_is_not_on_remote_surface() -> None:
    assert required_remote_scope("POST", "/api/v1/models/scan") is None
