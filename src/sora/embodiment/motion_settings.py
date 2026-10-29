"""Which motion engine moves her (Settings → Motion), applied when SORA next starts.

The owner wants the trained motion models selectable in SORA's GUI beside the current
algorithmic system, which stays the fallback (2026-10-25). The engines:

- ``algorithmic``: the hand-made poses and gait in her player (``StandInMotion``), the default;
- ``ardy``: NVIDIA's ARDY (Open Model licence), run by motion-lab's ``ardy-runtime`` on the GPU;
- ``custom``: one of motion-lab's own trained versions (``versions/vN``) at a size it has.

The motion models live in motion-lab, a separate folder (default: beside SORA's folder).
:mod:`sora.embodiment.motion_catalog` reads what actually exists there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from sora.contracts.base import StrictModel

MotionEngine = Literal["algorithmic", "ardy", "custom"]


class MotionSettings(StrictModel):
    engine: MotionEngine = "algorithmic"
    # ARDY: fp16 uses about 0.7 GB of video memory and adds a little jitter at rest; 4 diffusion
    # steps is the real-time setting on the owner's RX 9070 XT (motion-lab ardy-runtime README).
    ardy_precision: Literal["fp16", "fp32"] = "fp16"
    ardy_steps: int = Field(default=4, ge=2, le=10)
    custom_version: str = Field(default="v4", pattern=r"^v[0-9]{1,3}$")
    custom_size: str = Field(default="0.8M", pattern=r"^[0-9]{1,4}(\.[0-9]{1,2})?[MB]$")
    # Blank: a "motion-lab" folder beside SORA's own.
    lab_path: str = Field(default="", max_length=4096)


def resolve_lab(settings: MotionSettings, project: Path) -> Path:
    """The motion-lab folder (it may not exist)."""
    raw = settings.lab_path.strip()
    if not raw:
        return project.parent / "motion-lab"
    path = Path(raw)
    return path if path.is_absolute() else project / path
