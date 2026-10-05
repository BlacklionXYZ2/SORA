"""Versioned, credential-free owner settings staged for the next Core restart."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from sora.contracts.base import StrictModel
from sora.providers.dialogue import OpenAICompatibleDialogueProvider

from .model_catalog import normalize_model_folder


class EditableRuntimeSettings(StrictModel):
    version: Literal[1]
    dialogue_backend: Literal["deterministic", "openai-compatible"]
    dialogue_model: str | None = Field(default=None, max_length=200)
    dialogue_model_folder: Path | None = None
    dialogue_base_url: str | None = Field(default=None, max_length=2048)
    dialogue_timeout_seconds: float = Field(ge=1, le=300)
    worker_count: int = Field(ge=1, le=16)
    context_max_chars: int = Field(ge=256, le=65536)

    @field_validator("dialogue_model_folder")
    @classmethod
    def normalize_model_folder(cls, value: Path | None) -> Path | None:
        return normalize_model_folder(str(value)) if value is not None else None

    @model_validator(mode="after")
    def validate_dialogue(self) -> EditableRuntimeSettings:
        if self.dialogue_backend == "openai-compatible":
            if not self.dialogue_model or not self.dialogue_base_url:
                raise ValueError("OpenAI-compatible dialogue needs a model and /v1 URL")
            OpenAICompatibleDialogueProvider(
                base_url=self.dialogue_base_url, model=self.dialogue_model,
                timeout_seconds=self.dialogue_timeout_seconds,
            )
            if self.dialogue_model_folder is not None and urlparse(
                self.dialogue_base_url
            ).hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("a model folder requires a loopback dialogue endpoint")
        elif self.dialogue_model is not None or self.dialogue_base_url is not None:
            raise ValueError("deterministic dialogue cannot retain a model or endpoint")
        return self


class SavedRuntimeSettings(EditableRuntimeSettings):
    revision: int = Field(ge=1)


class RuntimeSettingsUpdate(EditableRuntimeSettings):
    expected_revision: int = Field(ge=0)


class RuntimeSettingsStore:
    def __init__(self, root: Path) -> None:
        self.path = root / "data" / "runtime-settings.json"

    def load(self) -> SavedRuntimeSettings | None:
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 16_384:
            raise ValueError("saved runtime settings exceed the size limit")
        return SavedRuntimeSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: SavedRuntimeSettings) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"runtime-settings.tmp-{uuid.uuid4().hex}")
        try:
            temporary.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            if temporary.exists():
                temporary.unlink()
