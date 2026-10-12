"""Decision layer preferences, stored with the rest of SORA's settings."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from sora.contracts.base import StrictModel

DEFAULT_RUNNER = Path(".local/decision/laya-v0.9.7/laya.exe")
DEFAULT_MODEL = Path(".local/decision/laya_english_q8_0.gguf")


class DecisionSettings(StrictModel):
    # shadow: Laya decides every message and the decision is logged beside what the brain
    # actually used, but every tool stays offered. enforce: the brain is offered only the chosen
    # families. Untrained Laya found every needed family in 24/24 test messages at 0.25.
    mode: Literal["off", "shadow", "enforce"] = "shadow"
    threshold: float = Field(default=0.25, ge=0.05, le=0.95)
    device: Literal["auto", "vulkan", "cpu"] = "auto"
    executable: str = Field(default="", max_length=4096)  # blank: the setup script's runner
    model_path: str = Field(default="", max_length=4096)  # blank: the setup script's GGUF


def resolve_paths(settings: DecisionSettings, project: Path) -> tuple[Path, Path]:
    runner = Path(settings.executable) if settings.executable else project / DEFAULT_RUNNER
    model = Path(settings.model_path) if settings.model_path else project / DEFAULT_MODEL
    return runner, model
