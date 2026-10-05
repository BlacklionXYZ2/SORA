"""Explicit, authenticated local llama.cpp process, independent of LM Studio."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field, field_validator, model_validator

from sora.contracts.base import StrictModel

CacheType = Literal["f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"]
GpuLayers = int | Literal["auto", "all"]


class SpeculativeOptions(StrictModel):
    type: Literal["none", "draft-mtp", "draft-dflash", "draft-eagle3", "draft-simple",
                  "ngram-simple", "ngram-map-k", "ngram-map-k4v", "ngram-mod",
                  "ngram-cache"] = "none"
    draft_model_path: Path | None = None
    draft_gpu_layers: GpuLayers = "auto"
    draft_cache_type_k: CacheType = "f16"
    draft_cache_type_v: CacheType = "f16"
    draft_tokens_min: int = Field(default=0, ge=0, le=256)
    draft_tokens_max: int = Field(default=3, ge=1, le=256)

    @model_validator(mode="after")
    def bounds(self) -> SpeculativeOptions:
        if self.draft_tokens_min > self.draft_tokens_max:
            raise ValueError("Draft minimum cannot exceed maximum")
        if isinstance(self.draft_gpu_layers, int) and not 0 <= self.draft_gpu_layers <= 999:
            raise ValueError("Draft GPU layers must be 0..999, auto, or all")
        return self


class LlamaOptions(StrictModel):
    """Serializable settings; file availability is checked at load, not at GUI boot."""

    executable: Path = Field(default_factory=lambda: Path("C:/llama.cpp/llama-server.exe"))
    model_path: Path | None = None
    mmproj_path: Path | None = None
    port: int = Field(default=18771, ge=1024, le=65535)
    context_size: int = Field(default=8192, ge=2048, le=131072)
    gpu_layers: GpuLayers = "auto"
    startup_timeout: float = Field(default=180, ge=1, le=600)
    flash_attn: Literal["auto", "on", "off"] = "auto"
    cache_type_k: CacheType = "f16"
    cache_type_v: CacheType = "f16"
    batch_size: int = Field(default=2048, ge=1, le=131072)
    ubatch_size: int = Field(default=512, ge=1, le=131072)
    split_mode: Literal["none", "layer", "row", "tensor"] = "layer"
    tensor_split: str = Field(default="", max_length=256, pattern=r"^([0-9.]+(,[0-9.]+)*)?$")
    main_gpu: int = Field(default=0, ge=0, le=63)
    cpu_moe: bool = False
    n_cpu_moe: int = Field(default=0, ge=0, le=999)
    load_mode: Literal["auto", "none", "mmap", "mlock", "mmap+mlock", "dio"] = "auto"
    swa_full: bool = False
    speculative: SpeculativeOptions = Field(default_factory=SpeculativeOptions)

    @model_validator(mode="after")
    def validate_options(self) -> LlamaOptions:
        if isinstance(self.gpu_layers, int) and not 0 <= self.gpu_layers <= 999:
            raise ValueError("GPU layers must be 0..999, auto, or all")
        if self.ubatch_size > self.batch_size:
            raise ValueError("Physical batch cannot exceed batch size")
        if self.flash_attn == "off" and self.cache_type_v not in {"f32", "f16", "bf16"}:
            raise ValueError("Quantized V cache requires flash attention; choose on or auto")
        if self.tensor_split:
            values = [float(value) for value in self.tensor_split.split(",")]
            if not any(values):
                raise ValueError("Tensor split must contain a positive weight")
        return self


class LlamaServerConfig(LlamaOptions):
    executable: Path
    model_path: Path
    mmproj_path: Path

    @field_validator("executable", "model_path", "mmproj_path")
    @classmethod
    def local_file(cls, value: Path) -> Path:
        if str(value).startswith(("\\\\", "//")):
            raise ValueError("llama.cpp paths must be local files")
        resolved = value.resolve(strict=True)
        if not resolved.is_file() or str(resolved).startswith(("\\\\", "//")):
            raise ValueError("llama.cpp paths must be local files")
        return resolved

    @model_validator(mode="after")
    def validate_models(self) -> LlamaServerConfig:
        if isinstance(self.gpu_layers, int) and not 0 <= self.gpu_layers <= 999:
            raise ValueError("gpu_layers must be 0..999, auto, or all")
        if self.model_path == self.mmproj_path:
            raise ValueError("model and projector must be separate files")
        for path in (self.model_path, self.mmproj_path):
            with path.open("rb") as stream:
                if path.suffix.lower() != ".gguf" or stream.read(4) != b"GGUF":
                    raise ValueError("model and projector must be GGUF files")
        spec = self.speculative
        if spec.type.startswith("draft-"):
            if spec.draft_model_path is None:
                raise ValueError("This speculative mode requires a compatible draft GGUF")
            draft = self.local_file(spec.draft_model_path)
            with draft.open("rb") as stream:
                if draft.suffix.lower() != ".gguf" or stream.read(4) != b"GGUF":
                    raise ValueError("Draft model must be GGUF")
        return self

    @classmethod
    def load(cls, path: Path) -> LlamaServerConfig:
        path = path.resolve(strict=True)
        if path.stat().st_size > 16_384:
            raise ValueError("llama.cpp configuration is too large")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            raise ValueError("llama.cpp configuration must be an object")
        for key in ("executable", "model_path", "mmproj_path"):
            if isinstance(payload.get(key), str):
                payload[key] = str(path.parent / payload[key])
        return cls.model_validate(payload)

    def command(self) -> list[str]:
        return llama_arguments(self)


def llama_arguments(options: LlamaOptions) -> list[str]:
    """One typed argument builder for launch and read-only preview; no file I/O."""
    if options.model_path is None or options.mmproj_path is None:
        raise ValueError("Select both the model and matching projector")
    command = [
        str(options.executable), "--model", str(options.model_path),
        "--mmproj", str(options.mmproj_path), "--host", "127.0.0.1",
        "--port", str(options.port), "--alias", "sora-local",
        "--ctx-size", str(options.context_size), "--parallel", "1",
        "--gpu-layers", str(options.gpu_layers), "--no-webui",
    ]
    for field, flag in {
        "flash_attn": "--flash-attn", "cache_type_k": "--cache-type-k",
        "cache_type_v": "--cache-type-v", "batch_size": "--batch-size",
        "ubatch_size": "--ubatch-size", "split_mode": "--split-mode",
        "main_gpu": "--main-gpu", "load_mode": "--load-mode",
    }.items():
        command.extend((flag, str(getattr(options, field))))
    if options.tensor_split:
        command.extend(("--tensor-split", options.tensor_split))
    if options.cpu_moe:
        command.append("--cpu-moe")
    if options.n_cpu_moe:
        command.extend(("--n-cpu-moe", str(options.n_cpu_moe)))
    if options.swa_full:
        command.append("--swa-full")
    spec = options.speculative
    command.extend(("--spec-type", spec.type))
    if spec.type.startswith("draft-"):
        if spec.draft_model_path is None:
            raise ValueError("Select a compatible draft GGUF for this speculative mode")
        command.extend(("--spec-draft-model", str(spec.draft_model_path),
                        "--spec-draft-ngl", str(spec.draft_gpu_layers),
                        "--spec-draft-type-k", spec.draft_cache_type_k,
                        "--spec-draft-type-v", spec.draft_cache_type_v,
                        "--spec-draft-n-min", str(spec.draft_tokens_min),
                        "--spec-draft-n-max", str(spec.draft_tokens_max)))
    return command


def public_llama_arguments(arguments: tuple[str, ...] | list[str]) -> list[str] | None:
    """Only the supported argument grammar, without environment/credentials/logs."""
    if not arguments or len(arguments) > 128 or sum(map(len, arguments)) > 32_768:
        return None
    if any(not argument or not argument.isprintable() for argument in arguments):
        return None
    pairs = {
        "--model", "--mmproj", "--host", "--port", "--alias", "--ctx-size", "--parallel",
        "--gpu-layers", "--flash-attn", "--cache-type-k", "--cache-type-v", "--batch-size",
        "--ubatch-size", "--split-mode", "--main-gpu", "--load-mode", "--tensor-split",
        "--n-cpu-moe", "--spec-type", "--spec-draft-model", "--spec-draft-ngl",
        "--spec-draft-type-k", "--spec-draft-type-v", "--spec-draft-n-min", "--spec-draft-n-max",
    }
    singles = {"--no-webui", "--cpu-moe", "--swa-full"}
    seen: set[str] = set()
    index = 1
    while index < len(arguments):
        flag = arguments[index]
        if flag in seen:
            return None
        seen.add(flag)
        if flag in singles:
            index += 1
        elif flag in pairs and index + 1 < len(arguments):
            if arguments[index + 1].startswith("--"):
                return None
            index += 2
        else:
            return None
    if not {"--model", "--mmproj", "--host", "--alias", "--no-webui"} <= seen:
        return None
    for flag, value in (("--host", "127.0.0.1"), ("--alias", "sora-local")):
        if arguments[arguments.index(flag) + 1] != value:
            return None
    return list(arguments)


def child_environment(api_key: str) -> dict[str, str]:
    # Parent model defaults must not disable the explicit projector or change bind/auth.
    env = {key: value for key, value in os.environ.items()
           if not key.upper().startswith("LLAMA_") and key.upper() != "LLVM_PATH"}
    env["LLAMA_API_KEY"] = api_key
    return env


class ManagedLlamaServer:
    def __init__(self, config: LlamaServerConfig, root: Path):
        self.config = config
        self.root = root.resolve()
        self.api_key = secrets.token_urlsafe(32)
        self.base_url = f"http://127.0.0.1:{config.port}/v1"
        self.process: asyncio.subprocess.Process | None = None
        self.launch_arguments: tuple[str, ...] | None = None

    async def inspect_runtime(self) -> str:
        """Check this installed binary's advertised flags before unloading a working model."""
        process = await asyncio.create_subprocess_exec(
            str(self.config.executable), "--help", stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, env=child_environment(self.api_key),
            cwd=self.root, creationflags=0x08000000 if os.name == "nt" else 0,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), timeout=10)
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            raise
        help_text = output.decode("utf-8", errors="replace")
        missing = [flag for flag in self.config.command()[1:]
                   if flag.startswith("--") and flag not in help_text]
        mode = self.config.speculative.type
        if mode != "none" and mode not in help_text:
            missing.append(mode)
        if process.returncode != 0 or missing:
            raise ValueError("Installed runtime does not advertise: " + ", ".join(missing)
                             if missing else "Installed runtime help probe failed")
        return "Requested flags are advertised; model compatibility still requires loading."

    async def start(self) -> None:
        # Reject occupied ports, even if the other service happens to report healthy.
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", self.config.port))
        log = self.root / "logs" / "llama-server.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        env = child_environment(self.api_key)
        env["SORA_LLAMA_CONFIG"] = self.config.model_dump_json()
        submitted_arguments = tuple(self.config.command())
        try:
            with log.open("ab") as output:
                self.process = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "sora.providers.llama_server", "--worker",
                    stdin=asyncio.subprocess.PIPE, stdout=output, stderr=output,
                    cwd=self.root, env=env,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
                # Submitted worker configuration, not independent OS/process attestation.
                self.launch_arguments = submitted_arguments
            async with asyncio.timeout(self.config.startup_timeout):
                async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
                    while True:
                        if self.process.returncode is not None:
                            raise RuntimeError(f"llama.cpp exited during loading; see {log}")
                        try:
                            response = await client.get(
                                f"{self.base_url}/models",
                                headers={"Authorization": f"Bearer {self.api_key}"},
                            )
                            if response.status_code == 200 and any(
                                item.get("id") == "sora-local"
                                for item in response.json().get("data", [])
                            ):
                                return
                        except (httpx.HTTPError, ValueError):
                            pass
                        await asyncio.sleep(0.25)
        except BaseException:
            await self.close()
            raise

    async def close(self) -> None:
        if self.process is None:
            self.launch_arguments = None
            return
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=15)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()
        self.process = None
        self.launch_arguments = None


def _worker() -> int:
    """Pipe EOF also stops the server if Core crashes or is forcibly terminated."""
    config = LlamaServerConfig.model_validate_json(os.environ.pop("SORA_LLAMA_CONFIG"))
    child = subprocess.Popen(
        config.command(), stdin=subprocess.DEVNULL,
        creationflags=0x08000000 if os.name == "nt" else 0,
    )

    def stop_on_eof() -> None:
        sys.stdin.buffer.read()
        if child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
            except ProcessLookupError:
                pass

    threading.Thread(target=stop_on_eof, daemon=True).start()
    return child.wait()


if __name__ == "__main__":
    if sys.argv[1:] != ["--worker"]:
        raise SystemExit("This module is launched by SORA with --llama-config.")
    raise SystemExit(_worker())
