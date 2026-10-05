"""Local llama.cpp lifecycle and explicit projector acceptance."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from sora.providers.llama_server import (
    LlamaOptions,
    LlamaServerConfig,
    ManagedLlamaServer,
    child_environment,
    llama_arguments,
    public_llama_arguments,
)
from sora.providers.mock import DeterministicProvider
from sora.runtime.service import RuntimeConfig, SoraRuntime
from sora.runtime.settings import RuntimeSettingsUpdate

IDENTITY_ROOT = Path(__file__).resolve().parents[2] / "identity"


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture
def config(tmp_path: Path) -> LlamaServerConfig:
    model, projector = tmp_path / "model.gguf", tmp_path / "mmproj.gguf"
    model.write_bytes(b"GGUFfixture")
    projector.write_bytes(b"GGUFfixture")
    return LlamaServerConfig(executable=Path(sys.executable), model_path=model,
                             mmproj_path=projector, port=free_port())


def test_explicit_parameters_and_clean_environment(
    config: LlamaServerConfig, monkeypatch: pytest.MonkeyPatch,
) -> None:
    command = config.command()
    assert command[command.index("--mmproj") + 1] == str(config.mmproj_path)
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--no-mmproj" not in command
    assert "--api-key" not in command
    monkeypatch.setenv("LLAMA_ARG_MMPROJ", "wrong")
    monkeypatch.setenv("LLAMA_ARG_HOST", "0.0.0.0")
    monkeypatch.setenv("LLVM_PATH", "conflicting-compiler")
    env = child_environment("temporary-key")
    assert env["LLAMA_API_KEY"] == "temporary-key"
    assert "LLAMA_ARG_MMPROJ" not in env and "LLAMA_ARG_HOST" not in env
    assert "LLVM_PATH" not in env
    assert os.environ["LLVM_PATH"] == "conflicting-compiler"


def test_configuration_rejects_missing_or_identical_projector(config: LlamaServerConfig) -> None:
    payload = config.model_dump()
    with pytest.raises(ValueError, match="separate files"):
        LlamaServerConfig.model_validate({**payload, "mmproj_path": config.model_path})
    with pytest.raises((ValueError, FileNotFoundError)):
        LlamaServerConfig.model_validate({**payload, "mmproj_path": "missing.gguf"})
    with pytest.raises(ValueError):
        LlamaServerConfig.model_validate({**payload, "gpu_layers": -1})


def test_read_only_preview_uses_the_launch_builder_without_file_validation(
    config: LlamaServerConfig,
) -> None:
    options = LlamaOptions.model_validate(config.model_dump())
    assert llama_arguments(options) == config.command()
    options = options.model_copy(update={
        "model_path": Path("C:/missing/folder with spaces/not-installed.gguf"),
        "mmproj_path": Path("C:/missing/projector.gguf"),
    })
    args = llama_arguments(options)
    assert args[args.index("--model") + 1] == str(options.model_path)
    assert public_llama_arguments(args) == args
    with pytest.raises(ValueError, match="both"):
        llama_arguments(LlamaOptions())
    options = options.model_copy(update={
        "speculative": options.speculative.model_copy(update={"type": "draft-mtp"}),
    })
    with pytest.raises(ValueError, match="draft GGUF"):
        llama_arguments(options)


@pytest.mark.parametrize("change", ["secret", "duplicate", "control", "too-large", "bind"])
def test_public_launch_grammar_refuses_unknown_credential_or_unreadable_arguments(
    config: LlamaServerConfig, change: str,
) -> None:
    args = config.command()
    if change == "secret":
        args.extend(("--api-key", "must-not-be-displayed"))
    elif change == "duplicate":
        args.extend(("--ctx-size", "2048"))
    elif change == "control":
        args[args.index("--model") + 1] = "C:/model\nsecret.gguf"
    elif change == "too-large":
        args[0] = "x" * 32769
    else:
        args[args.index("--host") + 1] = "0.0.0.0"
    assert public_llama_arguments(args) is None


def test_config_paths_resolve_relative_to_config_file(
    config: LlamaServerConfig, tmp_path: Path,
) -> None:
    path = tmp_path / "local.json"
    path.write_text(json.dumps({**config.model_dump(mode="json"),
                               "model_path": "model.gguf", "mmproj_path": "mmproj.gguf"}))
    assert LlamaServerConfig.load(path) == config
    path.write_text(json.dumps({**config.model_dump(mode="json"), "extra_args": ["--host"]}))
    with pytest.raises(ValueError, match="Extra inputs"):
        LlamaServerConfig.load(path)


class FakeProcess:
    returncode: int | None = None
    stdin: FakeProcess

    def __init__(self) -> None:
        self.stdin = self
        self.closed = False

    def close(self) -> None:
        self.closed = True
        self.returncode = 0

    async def wait(self) -> int:
        return self.returncode or 0

    def kill(self) -> None:
        self.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ready", [True, False])
async def test_managed_load_waits_and_cleans_up_on_success_or_timeout(
    config: LlamaServerConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ready: bool,
) -> None:
    fake = FakeProcess()
    calls: list[dict[str, Any]] = []

    async def spawn(*args: str, **kwargs: Any) -> FakeProcess:
        calls.append({"args": args, **kwargs})
        return fake

    monkeypatch.setattr("sora.providers.llama_server.asyncio.create_subprocess_exec", spawn)
    original_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda request: httpx.Response(
        200 if ready else 503, json={"data": [{"id": "sora-local"}]}, request=request,
    ))
    monkeypatch.setattr(httpx, "AsyncClient",
                        lambda **kwargs: original_client(transport=transport, **kwargs))
    server = ManagedLlamaServer(config.model_copy(update={"startup_timeout": 1}), tmp_path)
    if ready:
        await server.start()
        assert not fake.closed
        assert server.api_key not in str(calls[0]["args"])
        assert calls[0]["env"]["LLAMA_API_KEY"] == server.api_key
        assert calls[0]["stdin"] == asyncio.subprocess.PIPE
        submitted = tuple(config.command())
        assert server.launch_arguments == submitted
        server.config = server.config.model_copy(update={"context_size": 4096})
        assert server.launch_arguments == submitted  # capture is not rebuilt from replaced options
        assert server.api_key not in json.dumps(public_llama_arguments(submitted))
        await server.close()
    else:
        with pytest.raises(TimeoutError):
            await server.start()
    assert fake.closed
    assert server.launch_arguments is None


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_start_failure_or_cancellation_cleans_up(
    config: LlamaServerConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel: bool,
) -> None:
    fake = FakeProcess()
    if not cancel:
        fake.returncode = 1

    async def spawn(*args: str, **kwargs: Any) -> FakeProcess:
        return fake

    monkeypatch.setattr("sora.providers.llama_server.asyncio.create_subprocess_exec", spawn)
    server = ManagedLlamaServer(config, tmp_path)
    task = asyncio.create_task(server.start())
    if cancel:
        await asyncio.sleep(0)
        task.cancel()
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await task
    assert fake.closed
    assert server.process is None


@pytest.mark.asyncio
async def test_occupied_port_never_attaches_to_existing_server(
    config: LlamaServerConfig, tmp_path: Path,
) -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", config.port))
        listener.listen()
        server = ManagedLlamaServer(config, tmp_path)
        with pytest.raises(OSError):
            await server.start()
        assert server.process is None


@pytest.mark.asyncio
async def test_managed_model_overrides_saved_selection_without_overwriting_it(
    tmp_path: Path,
) -> None:
    root = tmp_path / "core"
    original = SoraRuntime(RuntimeConfig(root=root, identity_root=IDENTITY_ROOT),
                           provider=DeterministicProvider())
    await original.start()
    try:
        await original.stage_runtime_settings(RuntimeSettingsUpdate(
            version=1, expected_revision=0, dialogue_backend="openai-compatible",
            dialogue_model="old-lm-studio-model", dialogue_base_url="http://127.0.0.1:1234/v1",
            dialogue_timeout_seconds=90, worker_count=2, context_max_chars=8000,
        ))
    finally:
        await original.close()
    runtime = SoraRuntime(RuntimeConfig(
        root=root, identity_root=IDENTITY_ROOT,
        managed_dialogue=True, dialogue_backend="openai-compatible",
        dialogue_model="sora-local", dialogue_base_url="http://127.0.0.1:18771/v1",
        dialogue_api_key=SecretStr("never-persist-this"),
    ), provider=DeterministicProvider())
    await runtime.start()
    try:
        assert runtime.config.dialogue_model == "sora-local"
        payload = runtime.editable_runtime_settings().model_dump()
        await runtime.stage_runtime_settings(RuntimeSettingsUpdate(
            **{**payload, "worker_count": 3}, expected_revision=1,
        ))
        saved = runtime.settings_store.load()
        assert saved is not None and saved.dialogue_model == "old-lm-studio-model"
        assert saved.worker_count == 3
        assert "never-persist-this" not in runtime.settings_store.path.read_text()
        pending = runtime.runtime_settings_view()["pending_settings"]
        assert isinstance(pending, dict) and pending["dialogue_model"] == "sora-local"
        with pytest.raises(ValueError, match="--llama-config"):
            await runtime.stage_runtime_settings(RuntimeSettingsUpdate(
                **{**payload, "dialogue_model": "other"}, expected_revision=2,
            ))
    finally:
        await runtime.close()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("SORA_TEST_LLAMA_CONFIG"), reason="opt-in real GGUF/projector load",
)
async def test_live_local_model_with_explicit_projector(tmp_path: Path) -> None:
    from tests.vision.test_capture import png

    from sora.api import ApiServerConfig, SoraApiServer

    config = LlamaServerConfig.load(Path(os.environ["SORA_TEST_LLAMA_CONFIG"]))
    server = ManagedLlamaServer(config.model_copy(update={"port": free_port()}), tmp_path)
    runtime = SoraRuntime(RuntimeConfig(
        root=tmp_path, identity_root=IDENTITY_ROOT,
        managed_dialogue=True, dialogue_backend="openai-compatible",
        dialogue_model="sora-local", dialogue_base_url=server.base_url,
        dialogue_api_key=SecretStr(server.api_key), dialogue_timeout_seconds=90,
    ), provider=DeterministicProvider())
    api = SoraApiServer(runtime, ApiServerConfig(port=0, auth_token="local-test-token"))
    try:
        await server.start()
        await runtime.start()
        await api.start()
        async with httpx.AsyncClient(timeout=100, trust_env=False) as client:
            denied = await client.get(server.base_url + "/models")
            assert denied.status_code == 401
            for color, rgba in (("red", (255, 0, 0, 255)), ("blue", (0, 0, 255, 255))):
                # Neutral filename: the answer must come from image pixels, not path metadata.
                target = tmp_path / "image.png"
                target.write_bytes(png(256, 256, rgba))
                response = await client.post(
                    f"http://127.0.0.1:{api.actual_port}/api/v1/dialogue",
                    headers={"Authorization": "Bearer local-test-token"},
                    json={"content": "Name the dominant color in this image in one word.",
                          "file_paths": [str(target)]},
                )
                assert response.status_code == 201, response.text
                answer = response.json()["response"]
                print(f"Live explicit-projector answer ({color} fixture): {answer}")
                assert color in answer.lower()
    finally:
        await api.close()
        await runtime.close()
        await server.close()
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", server.config.port)) != 0
