"""Memory manager preferences, stored with the rest of SORA's settings (Settings → Memory)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from sora.contracts.base import StrictModel

DEFAULT_SERVER = Path(".local/llama.cpp-b11516/llama-server.exe")
DEFAULT_MODEL = Path(".local/models/embeddinggemma-2/embeddinggemma-2-UD-Q4_K_XL.gguf")


class MemoryManagerSettings(StrictModel):
    # on (default since 2026-10-10): her prompts recall memories by meaning; it found 30/30 in
    # the probe, and live recency recall lost older facts. shadow: meaning-based recall is only
    # recorded beside the simpler recall, for comparison. off: not used. In every mode
    # memories are embedded, linked and every decision is logged for training.
    mode: Literal["off", "shadow", "on"] = "on"
    device: Literal["gpu", "cpu"] = "gpu"
    server: str = Field(default="", max_length=4096)  # blank: the llama.cpp build for embeddings
    model_path: str = Field(default="", max_length=4096)  # blank: EmbeddingGemma 2 Q4_K_XL


def resolve_paths(settings: MemoryManagerSettings, project: Path) -> tuple[Path, Path]:
    server = Path(settings.server) if settings.server else project / DEFAULT_SERVER
    model = Path(settings.model_path) if settings.model_path else project / DEFAULT_MODEL
    return server, model
