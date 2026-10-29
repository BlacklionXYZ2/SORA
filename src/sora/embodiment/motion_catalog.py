"""What motion engines, trained versions and sizes exist, for the Motion window.

motion-lab is the source of truth: its ``tools/motion_catalog.py`` writes ``catalog.json`` (and
small preview clips beside it) from what is actually on disk, with the measurements each
model's evaluation produced. Core reads it, validates it against :class:`MotionCatalog`, checks
the files it names still exist, and adds the always-available algorithmic system.

Nothing here runs a model. A missing or unreadable motion-lab gives a catalogue with only the
algorithmic engine, and a note saying why.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, ValidationError

from sora.contracts.base import StrictModel
from sora.embodiment.motion_settings import MotionSettings, resolve_lab

CATALOG_FILE = "catalog/catalog.json"
MAX_CATALOG_BYTES = 1_048_576
MAX_PREVIEW_BYTES = 2_097_152
PREVIEW_PATTERN = r"^previews/[A-Za-z0-9_.-]+\.json$"
PREVIEW_NAME = re.compile(PREVIEW_PATTERN)


class MotionMeasures(StrictModel):
    """One model's numbers on motion-lab's 60 s evaluation (``m1_eval.measures``); None where
    that evaluation didn't measure it."""

    outside_limits_share: float | None = Field(default=None, ge=0, le=1)
    foot_slide_m_s: float | None = Field(default=None, ge=0)
    jitter_m_s3: float | None = Field(default=None, ge=0)
    energy_rad_s: float | None = Field(default=None, ge=0)
    walk_speed_m_s: float | None = Field(default=None, ge=0)
    step_latency_ms: float | None = Field(default=None, ge=0)
    video_memory_gb: float | None = Field(default=None, ge=0)
    note: str = Field(default="", max_length=600)


class MotionModel(StrictModel):
    """One selectable model: an engine variant or a trained version at one size."""

    version: str = Field(max_length=32)
    size: str = Field(max_length=16)
    parameters: int | None = Field(default=None, ge=0)
    state: Literal["ready", "experimental", "missing", "planned"]
    summary: str = Field(default="", max_length=600)
    measures: MotionMeasures = Field(default_factory=MotionMeasures)
    preview: str | None = Field(default=None, max_length=200, pattern=PREVIEW_PATTERN)
    files: list[str] = Field(default_factory=list, max_length=16)


class MotionEngineEntry(StrictModel):
    id: Literal["algorithmic", "ardy", "custom"]
    name: str = Field(max_length=80)
    summary: str = Field(default="", max_length=600)
    licence: str = Field(default="", max_length=200)
    models: list[MotionModel] = Field(default_factory=list, max_length=64)


class MotionCatalog(StrictModel):
    """The Motion window's catalogue (``GET /api/v1/motion/catalog``)."""

    version: Literal[1] = 1
    generated: str = Field(default="", max_length=40)
    lab_path: str = Field(default="", max_length=4096)
    lab_found: bool = False
    note: str = Field(default="", max_length=600)
    recordings: MotionMeasures = Field(default_factory=MotionMeasures)
    engines: list[MotionEngineEntry] = Field(default_factory=list, max_length=8)


ALGORITHMIC = MotionEngineEntry(
    id="algorithmic",
    name="Algorithmic",
    summary=(
        "Her hand-made poses and gait in the player: standing, walking, running, sitting, "
        "leaning, falling and getting up. Always available, and the fallback."
    ),
    models=[MotionModel(version="built-in", size="", state="ready",
                        summary="Deterministic poses; no model to load.")],
)


def load_catalog(settings: MotionSettings, project: Path) -> MotionCatalog:
    """The catalogue from motion-lab, with the algorithmic engine first. Files a model names
    that no longer exist mark it ``missing``."""
    lab = resolve_lab(settings, project)
    path = lab / CATALOG_FILE
    base = MotionCatalog(lab_path=str(lab), lab_found=lab.is_dir(), engines=[ALGORITHMIC])
    if not path.is_file():
        note = ("motion-lab was not found." if not lab.is_dir() else
                "motion-lab has no catalog yet: run tools\\motion_catalog.py there.")
        return base.model_copy(update={"note": note})
    try:
        if path.stat().st_size > MAX_CATALOG_BYTES:
            raise ValueError("catalog.json is larger than 1 MiB")
        lab_catalog = MotionCatalog.model_validate(json.loads(path.read_text("utf-8")))
    except (OSError, ValueError, ValidationError) as exc:
        note = f"motion-lab's catalog couldn't be read: {exc}"[:600]
        return base.model_copy(update={"note": note})
    engines = [ALGORITHMIC]
    for engine in lab_catalog.engines:
        if engine.id == "algorithmic":
            continue
        models = [
            model.model_copy(update={"state": "missing"})
            if model.state in {"ready", "experimental"}
            and any(not (lab / name).exists() for name in model.files)
            else model
            for model in engine.models
        ]
        engines.append(engine.model_copy(update={"models": models}))
    return lab_catalog.model_copy(update={"lab_path": str(lab), "lab_found": True,
                                          "engines": engines})


def load_preview(settings: MotionSettings, project: Path, name: str) -> dict[str, object]:
    """A preview clip named by the catalogue (``previews/<file>.json``), as stored."""
    if not PREVIEW_NAME.fullmatch(name):
        raise ValueError("not a catalogue preview name")
    path = resolve_lab(settings, project) / "catalog" / name
    if not path.is_file():
        raise FileNotFoundError(name)
    if path.stat().st_size > MAX_PREVIEW_BYTES:
        raise ValueError("preview is larger than 2 MiB")
    data = json.loads(path.read_text("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("preview must be an object")
    return data
