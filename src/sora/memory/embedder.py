"""The memory embedder: EmbeddingGemma 2 served by its own llama.cpp process.

EmbeddingGemma 2 needs llama.cpp b11516 or newer, which is newer than the brain's build, so it
runs as a separate small server (about 0.2 GB of VRAM for text; the image/audio projector adds
about 0.55 GB and is loaded only when media parts are embedded). Everything that compares
memories goes through this one class, so the probe, the manager and training see the same
vectors.

Task prefixes come from the model card: a search query and a stored document are embedded
differently (asymmetric retrieval), and "sentence similarity" is used when two memories are
compared with each other.
"""

from __future__ import annotations

import asyncio
import base64
import math
import os
import secrets
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import httpx

from sora import helper_processes
from sora.memory.vectors import Vector, unit
from sora.providers.llama_server import free_local_port

QUERY = "task: search result | query: {}"
DOCUMENT = "title: {title} | text: {text}"
SIMILARITY = "task: sentence similarity | query: {}"
Role = Literal["query", "document", "similarity"]


class EmbedderError(RuntimeError):
    pass


class Embedder(Protocol):
    """Any embedder Core can use; swapping it re-embeds every memory (``identity`` changes)."""

    identity: str
    dims: int
    modalities: frozenset[str]  # "text", and "image"/"audio" when it can embed them

    async def embed(self, text: str, role: Role, *, title: str = "none") -> Vector: ...

    async def embed_media(self, data: bytes, kind: Literal["image", "audio"]) -> Vector: ...

    async def embed_mixed(self, text: str, role: Role, media: Sequence[bytes]) -> Vector: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class EmbedderConfig:
    server: Path
    model: Path
    mmproj: Path | None = None  # image/audio; None keeps the embedder text-only and small
    dims: int = 512  # Matryoshka cut; 256-512 were as good as 768 in the probe
    gpu_layers: str = "99"  # "0" runs on the CPU
    port: int = 18890
    start_timeout: float = 120
    log: Path | None = None


class LlamaEmbedder:
    def __init__(self, config: EmbedderConfig) -> None:
        self.config = config
        self.dims = config.dims
        self.identity = f"{config.model.stem}@{config.dims}"
        self.modalities = frozenset({"text"} | ({"image", "audio"} if config.mmproj else set()))
        self.state, self.reason = "stopped", ""
        self.process: asyncio.subprocess.Process | None = None
        self._client: httpx.AsyncClient | None = None
        self._marker = ""
        self._api_key = secrets.token_urlsafe(24)
        self._lock = asyncio.Lock()

    def available(self) -> bool:
        return self.config.server.is_file() and self.config.model.is_file()

    async def start(self) -> None:
        async with self._lock:
            if self.process is not None and self.process.returncode is None:
                return
            if not self.available():
                self.state, self.reason = "unavailable", "Run scripts/setup-memory-embedder.ps1"
                raise EmbedderError(self.reason)
            port = free_local_port(self.config.port)
            argv = [str(self.config.server), "-m", str(self.config.model), "--embeddings",
                    "--pooling", "mean", "-c", "8192", "-b", "8192", "-ub", "8192",
                    "--parallel", "1", "-ngl", self.config.gpu_layers, "--host", "127.0.0.1",
                    "--port", str(port), "--api-key", self._api_key]
            if self.config.mmproj is not None:
                argv[3:3] = ["--mmproj", str(self.config.mmproj)]
            self.state = "starting"
            log = self.config.log
            if log is not None:
                log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("ab") if log is not None else open(os.devnull, "wb") as output:
                self.process = await asyncio.create_subprocess_exec(
                    *argv, stdin=asyncio.subprocess.DEVNULL, stdout=output, stderr=output,
                    creationflags=0x08000000 if os.name == "nt" else 0,
                )
            helper_processes.record("embedder", getattr(self.process, "pid", None))
            self._client = httpx.AsyncClient(
                base_url=f"http://127.0.0.1:{port}", timeout=60, trust_env=False,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            try:
                async with asyncio.timeout(self.config.start_timeout):
                    while True:
                        if self.process.returncode is not None:
                            raise EmbedderError("the embedding server exited while loading")
                        try:
                            if (await self._client.get("/health")).status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        await asyncio.sleep(0.25)
                props = (await self._client.get("/props")).json()
                self._marker = str(props.get("media_marker", ""))
            except (TimeoutError, EmbedderError, httpx.HTTPError, ValueError) as exc:
                await self._stop()
                self.state, self.reason = "failed", f"could not start ({exc})"
                raise EmbedderError(self.reason) from exc
            self.state, self.reason = "ready", ""

    async def embed(self, text: str, role: Role, *, title: str = "none") -> Vector:
        """``title`` applies to stored documents only (the model card's document form)."""
        clean = " ".join(text.split())
        if role == "document":
            return await self._embed(DOCUMENT.format(title=title, text=clean))
        return await self._embed((QUERY if role == "query" else SIMILARITY).format(clean))

    async def embed_media(self, data: bytes, kind: Literal["image", "audio"]) -> Vector:
        if self.config.mmproj is None:
            raise EmbedderError(f"this embedder is text-only; {kind} needs the projector")
        await self.start()
        content = [{"prompt_string": self._marker,
                    "multimodal_data": [base64.b64encode(data).decode()]}]
        return await self._embed(content)

    async def embed_mixed(self, text: str, role: Role, media: Sequence[bytes]) -> Vector:
        """One embedding of text with images and recordings together (interleaved input)."""
        if self.config.mmproj is None:
            raise EmbedderError("this embedder is text-only")
        await self.start()
        clean = " ".join(text.split())
        prompt = (DOCUMENT.format(title="none", text=clean) if role == "document" else
                  (QUERY if role == "query" else SIMILARITY).format(clean))
        content = [{"prompt_string": prompt + "".join(f" {self._marker}" for _ in media),
                    "multimodal_data": [base64.b64encode(item).decode() for item in media]}]
        return await self._embed(content)

    async def _embed(self, content: object) -> Vector:
        await self.start()
        assert self._client is not None
        try:
            reply = await self._client.post("/embeddings", json={"content": content})
            reply.raise_for_status()
            data = reply.json()
            item = data[0] if isinstance(data, list) else data["data"][0]
            embedding = item["embedding"]
            vector: Sequence[float] = embedding[0] if isinstance(embedding[0], list) else embedding
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise EmbedderError(f"embedding failed ({exc})") from exc
        if any(math.isnan(value) for value in vector):
            raise EmbedderError("the embedding contained NaN")
        return unit(vector, self.dims)

    async def close(self) -> None:
        async with self._lock:
            await self._stop()
            self.state, self.reason = "stopped", ""

    async def _stop(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()
        process, self.process = self.process, None
        if process is None or process.returncode is not None:
            return
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            process.kill()
            await process.wait()
